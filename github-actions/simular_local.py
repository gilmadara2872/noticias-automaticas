#!/usr/bin/env python3
"""
Simulação local do sistema de notícias - testa exportação CSV/JSON
sem precisar do Supabase. Gera dados falsos realistas.
Uso:
  python simular_local.py
  python simular_local.py --dias 30 --csv --json
"""
import os
import sys
import json
import random
import argparse
from datetime import datetime, timedelta, timezone

BRT = timezone(timedelta(hours=-3))

VEICULOS = ["G1", "UOL", "Folha de S.Paulo", "O Globo", "Estadão", "Valor Econômico", "CNN Brasil", "Reuters"]
SENTIMENTOS = ["POSITIVA", "NEGATIVA", "NEUTRA"]

NOTICIAS_BASE = [
    ("Nova parceria internacional anunciada", "POSITIVA"),
    ("Empresa registra crescimento de 20% no trimestre", "POSITIVA"),
    ("Projeto de lei é aprovado no congresso", "NEUTRA"),
    ("Mercado financeiro reage positivamente", "POSITIVA"),
    ("Investimento em tecnologia bate recorde", "POSITIVA"),
    ("Crise política afeta negociações", "NEGATIVA"),
    ("Queda nas vendas preocupa investidores", "NEGATIVA"),
    ("Nova regulamentação entra em vigor", "NEUTRA"),
    ("Empresa é multada por irregularidades", "NEGATIVA"),
    ("Expansão para novos mercados confirmada", "POSITIVA"),
    ("Acidente em fábrica deixa feridos", "NEGATIVA"),
    ("Fusão entre empresas é anunciada", "NEUTRA"),
    ("Lucro líquido supera expectativas", "POSITIVA"),
    ("Processo judicial movido contra empresa", "NEGATIVA"),
    ("Lançamento de produto inovador", "POSITIVA"),
]

def gerar_noticias(qtd=50, dias=7):
    """Gera notícias falsas realistas"""
    noticias = []
    agora = datetime.now(BRT)
    
    for i in range(qtd):
        base, sentimento_base = random.choice(NOTICIAS_BASE)
        veiculo = random.choice(VEICULOS)
        
        # Data aleatória nos últimos N dias
        offset_dias = random.randint(0, dias-1)
        offset_horas = random.randint(0, 23)
        quando = agora - timedelta(days=offset_dias, hours=offset_horas)
        
        # Varia o sentimento às vezes
        sentimento = sentimento_base if random.random() > 0.3 else random.choice(SENTIMENTOS)
        
        noticias.append({
            "ts": quando.isoformat(),
            "quando": quando.isoformat(),
            "dia": quando.strftime("%Y-%m-%d"),
            "source": veiculo,
            "title": f"{base} - {veiculo}",
            "link": f"https://exemplo.com/noticia/{i}",
            "sentimento": sentimento
        })
    
    # Ordenar por data desc
    noticias.sort(key=lambda x: x["ts"], reverse=True)
    return noticias

def para_csv(noticias):
    """Converte para CSV"""
    linhas = ["ts,quando,source,title,link,sentimento"]
    for n in noticias:
        titulo = n["title"].replace('"', "'")
        linhas.append(f'"{n["ts"]}","{n["quando"]}","{n["source"]}","{titulo}","{n["link"]}","{n["sentimento"]}"')
    return "\n".join(linhas)

def para_json(noticias):
    """Gera resumo JSON"""
    summary = {
        "total": len(noticias),
        "por_sentimento": {"POSITIVA": 0, "NEGATIVA": 0, "NEUTRA": 0},
        "por_fonte": {},
        "por_dia": {},
        "noticias": []
    }
    
    for n in noticias:
        s = n["sentimento"]
        summary["por_sentimento"][s] = summary["por_sentimento"].get(s, 0) + 1
        
        src = n["source"]
        summary["por_fonte"][src] = summary["por_fonte"].get(src, 0) + 1
        
        dia = n["dia"]
        summary["por_dia"][dia] = summary["por_dia"].get(dia, 0) + 1
        
        summary["noticias"].append({
            "quando": n["quando"],
            "source": src,
            "title": n["title"],
            "link": n["link"],
            "sentimento": s
        })
    
    return summary

def main():
    parser = argparse.ArgumentParser(description="Simulação local de notícias")
    parser.add_argument("--dias", type=int, default=7, help="Dias para simular (default: 7)")
    parser.add_argument("--qtd", type=int, default=50, help="Quantidade de notícias (default: 50)")
    parser.add_argument("--csv", action="store_true", help="Gerar CSV")
    parser.add_argument("--json", action="store_true", help="Gerar JSON")
    parser.add_argument("--output", help="Nome do arquivo de saída")
    
    args = parser.parse_args()
    
    print("=" * 50)
    print("  SIMULAÇÃO LOCAL - SISTEMA DE NOTÍCIAS")
    print("=" * 50)
    
    noticias = gerar_noticias(args.qtd, args.dias)
    
    print(f"\n✓ {len(noticias)} notícias geradas (últimos {args.dias} dias)")
    
    # Mostrar resumo
    sentimentos = {"POSITIVA": 0, "NEGATIVA": 0, "NEUTRA": 0}
    for n in noticias:
        sentimentos[n["sentimento"]] += 1
    
    print(f"  - Positivas: {sentimentos['POSITIVA']}")
    print(f"  - Negativas: {sentimentos['NEGATIVA']}")
    print(f"  - Neutras: {sentimentos['NEUTRA']}")
    
    if args.csv:
        csv_content = para_csv(noticias)
        nome = args.output or f"simulacao_noticias_{datetime.now(BRT).strftime('%Y%m%d_%H%M%S')}.csv"
        with open(nome, 'w', encoding='utf-8') as f:
            f.write(csv_content)
        print(f"\n✓ CSV salvo: {nome}")
    
    if args.json:
        json_data = para_json(noticias)
        nome = args.output or f"simulacao_noticias_{datetime.now(BRT).strftime('%Y%m%d_%H%M%S')}.json"
        with open(nome, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)
        print(f"\n✓ JSON salvo: {nome}")
    
    if not args.csv and not args.json:
        print("\nUse --csv e/ou --json para exportar")
    
    print("\n" + "=" * 50)

if __name__ == "__main__":
    main()