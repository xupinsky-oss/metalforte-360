import io
import os
import unittest
from unittest.mock import patch
import pandas as pd
import requests
from openpyxl import Workbook
from src import data
from src.data_catalog import object_path
from src.cloud_storage import is_missing_object_error


def mapping_file():
    workbook=Workbook()
    seller=workbook.active
    seller.title="DE_PARA_VENDEDOR"
    seller.append(["VENDEDOR CADASTRO","CLASSIFICAÇÃO","VENDEDOR PAINEL"])
    seller.append(["ANA","INTERNO","EQUIPE ANA"])
    client=workbook.create_sheet("DE_PARA_CLIENTE")
    client.append([None,None,None,None])
    client.append(["Cód. Cliente","Lj Cliente","Cliente","GRUPO ECONOMICO"])
    client.append(["000001","01","EMPRESA UM","GRUPO UM"])
    client.append(["000002","01","EMPRESA DOIS",None])
    output=io.BytesIO();workbook.save(output)
    return output.getvalue()


class DataPipelineTests(unittest.TestCase):
    def setUp(self):
        data.set_depara_version("legacy")

    def tearDown(self):
        data.clear_depara_cache();data.set_depara_version(None)

    def test_blank_header_and_unmapped_customer_are_preserved(self):
        payload,counts=data.prepare_depara_upload(mapping_file())
        self.assertEqual(counts,{"clientes":2,"vendedores":1})
        customers=pd.read_excel(io.BytesIO(payload),sheet_name="DE_PARA_CLIENTE",dtype=str)
        self.assertIn("GRUPO ECONOMICO",customers)

    def test_numeric_codes_and_group_fallback_reconcile_without_changing_totals(self):
        with patch.object(data,"is_configured",return_value=True),patch.object(data,"download_bytes",return_value=mapping_file()):
            source=pd.DataFrame({"Cod Cliente":[1,2],"Cliente":["OUTRO NOME","EMPRESA DOIS"],"Vendedor":["Ana","ANA"],"Faturamento":[10,20]})
            result=data.apply_depara(source)
            self.assertEqual(result["Cliente Painel"].tolist(),["GRUPO UM","EMPRESA DOIS"])
            self.assertEqual(result["Status DE/PARA Cliente"].tolist(),["Com grupo","Sem grupo"])
            self.assertEqual(result["Vendedor Painel"].tolist(),["EQUIPE ANA"]*2)
            self.assertEqual(result["Faturamento"].sum(),source["Faturamento"].sum())

    def test_reference_version_recovers_from_missing_file(self):
        with patch.object(data,"is_configured",return_value=True),patch.object(data,"download_bytes",side_effect=[OSError(),mapping_file()]):
            data.set_depara_version("missing")
            self.assertFalse(data.depara_available())
            data.set_depara_version("new-etag")
            self.assertTrue(data.depara_available())

    def test_environment_paths_stay_together(self):
        with patch.dict(os.environ,{"SUPABASE_DATA_PATH":"bases/homologacao/metalforte_base.csv.gz"},clear=True):
            self.assertEqual(object_path("targets"),"bases/homologacao/metalforte_metas.xlsx")
            self.assertEqual(object_path("orders"),"bases/homologacao/metalforte_pedidos_realizado.csv.gz")

    def test_missing_storage_object_uses_error_code_even_with_http_400(self):
        response = requests.Response()
        response.status_code = 400
        response._content = b'{"statusCode":"404","code":"NoSuchKey","message":"Object not found"}'
        self.assertTrue(is_missing_object_error(requests.HTTPError(response=response)))

        response._content = b'{"statusCode":"400","code":"InvalidKey","message":"Bad request"}'
        self.assertFalse(is_missing_object_error(requests.HTTPError(response=response)))

    def test_cloud_failure_does_not_use_local_base(self):
        with patch.object(data,"is_configured",return_value=True),patch.object(data,"download_bytes",side_effect=OSError()),patch.object(data.pd,"read_csv") as read:
            result=data._read_dataset("targets")
            self.assertTrue(result.empty)
            self.assertEqual(result.attrs["load_error"],"OSError")
            read.assert_not_called()

    def test_publish_checks_download_integrity(self):
        with patch.object(data,"upload_bytes",return_value=True),patch.object(data,"download_bytes",return_value=b"different"):
            with self.assertRaisesRegex(RuntimeError,"integridade"):
                data.publish_depara(mapping_file())

    def test_database_is_preferred_without_downloading_excel(self):
        snapshot={"ready":True,"sellers":[["ANA","EQUIPE ANA","INTERNO"]],"customers":[["000001","01","EMPRESA UM","GRUPO UM"]]}
        data.set_depara_version("db:12")
        with patch.object(data,"is_configured",return_value=True),patch.object(data,"depara_rpc",return_value=snapshot),patch.object(data,"download_bytes") as file:
            source=pd.DataFrame({"Cod Cliente":[1],"Cliente":["EMPRESA UM"],"Vendedor":["ANA"]})
            result=data.apply_depara(source)
            self.assertEqual(result["Cliente Painel"].tolist(),["GRUPO UM"])
            self.assertEqual(result["Vendedor Painel"].tolist(),["EQUIPE ANA"])
            file.assert_not_called()

    def test_database_revision_is_the_cache_key(self):
        with patch.object(data,"is_configured",return_value=True),patch.object(data,"depara_rpc",return_value={"ready":True,"version":24}):
            self.assertEqual(data.depara_reference_version(),"db:24")

    def test_unavailable_database_never_falls_back_to_stale_excel(self):
        data.set_depara_version("db:12")
        with patch.object(data,"is_configured",return_value=True),patch.object(data,"depara_rpc",side_effect=OSError()),patch.object(data,"download_bytes") as file:
            self.assertFalse(data.depara_available())
            file.assert_not_called()

    def test_legacy_upload_cannot_override_active_database(self):
        with patch.object(data,"depara_reference_version",return_value="db:12"),patch.object(data,"upload_bytes") as upload:
            with self.assertRaisesRegex(RuntimeError,"tabelas"):
                data.publish_depara(mapping_file())
            upload.assert_not_called()

if __name__=="__main__":
    unittest.main()
