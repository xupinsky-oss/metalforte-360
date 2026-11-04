# Monitor local do fluxo METALFORTE 360

Painel independente do Streamlit. Ele consulta GitHub Actions, a telemetria privada do Supabase e a verificação de saúde pública do Streamlit; os segredos são usados apenas pelo servidor local.

## Iniciar

Abra PowerShell na pasta do projeto e execute:

```powershell
py -3.14 monitor/server.py
```

O monitor usa apenas a biblioteca padrão do Python; qualquer versão 3.11 ou posterior serve. O navegador abre em `http://127.0.0.1:8765`. Também é possível abrir `monitor/iniciar_monitor.bat` no Explorador de Arquivos para iniciar o painel.

## Conectar as fontes privadas

1. Para o GitHub, entre uma vez pelo GitHub CLI: `gh auth login`. O monitor usa a sessão local do CLI para leitura das execuções e do código. É necessário ter acesso de leitura a Actions e ao repositório `xupinsky-oss/metalforte-360`.
2. Para o Supabase, crie `monitor/.env.monitor` copiando `monitor/.env.monitor.example` e preencha `SUPABASE_URL` e `SUPABASE_SERVICE_KEY` com os valores já usados no projeto. Esse arquivo é ignorado pelo Git. Nunca cole a chave na página do navegador, em issue ou em commit.
3. Se o repositório já tiver `.streamlit/secrets.toml` local, o monitor também pode ler essas mesmas configurações sem copiá-las. O arquivo não deve ser commitado.
4. Reabra/atualize o painel. A consulta automática ocorre a cada 60 segundos.

## O que cada fonte informa

- **GoodData:** horário da etapa de extração registrada pela telemetria. A integração atual não expõe a versão própria do relatório; por isso o painel mostra o identificador do relatório e deixa a versão como indisponível.
- **Python:** versão do runtime declarada no workflow (hoje Python 3.12) e horário da última execução.
- **GitHub Actions:** versão do código na branch configurada, execuções recentes, resultado e links para logs protegidos.
- **Supabase:** horário da base publicada e telemetria sanitizada armazenada no bucket privado.
- **Streamlit:** teste do endpoint público de saúde. A versão implantada não é exposta por esse endpoint, então o painel mostra a versão do código esperada em separado, sem afirmar que já foi implantada.

O próximo horário é a próxima janela de tentativa (:17 ou :47, no fuso de São Paulo), respeitando o bloqueio de 55 minutos após uma execução bem-sucedida. O agendamento do GitHub é de melhor esforço, portanto não é garantia de início exatamente naquele minuto. Os erros apresentados vêm da telemetria sanitizada e do estado das execuções; os logs detalhados ficam no GitHub e abrem com a autenticação normal da sua conta.

O servidor se liga somente a `127.0.0.1`; este painel não é publicado nem fica acessível a outras pessoas na rede.

Para ver o mapa completo das informações, programas, destinos e horários, consulte [MAPA_DO_FLUXO.md](MAPA_DO_FLUXO.md). A mesma ilustração também aparece no começo do painel Monitor.
