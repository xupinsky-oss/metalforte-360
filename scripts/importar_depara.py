"""Importa a referência corporativa usando as mesmas validações do app."""
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.data import publish_depara

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("arquivo", type=Path)
    args = parser.parse_args()
    counts = publish_depara(args.arquivo.read_bytes())
    print(f"DE/PARA publicado e conferido: {counts['clientes']} clientes, {counts['vendedores']} vendedores.")
