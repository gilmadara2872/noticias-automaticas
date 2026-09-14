#!/usr/bin/env python3
"""
Script de teste/simulação para o monitoramento de notícias.
Uso:
  python test_simulation.py --keywords "Python;Machine Learning" --days 7
"""
import os
import sys
import json
import argparse
from datetime import datetime, timedelta

# Adicionar path
sys.path.insert(0, os.path.dirname(__file__))

import common
import monitor

def simular_coleta(keywords, dias=7):
    """Simula a coleta de notícias para teste"""
    print(f"\n=== SIMULANDO COLETA DE NOTÍCIAS ===")
    print(f"Palavras-chave: {keywords}")
    print(f"Dias a manter: {dias}")
    
    # Substituir KEYWORDS temporariamente
    old_keywords = common.KEYWORDS
    common.KEYWORDS = [k.strip() for k in keywords.split(';')]
    
    try:
        count = monitor.main()
        print(f"\n✓ Coleta concluída: {count} notícias novas")
        return count
    finally:
        common.KEYWORDS = old_keywords

def gerar_csv(dias=7, output=None):
    """Exporta notícias para CSV"""
    from datetime import datetime, timedelta, timezone
    
    BRT = timezone(timedelta(hours=-3))
    alvo = datetime.now(BRT) - timedelta(days=dias)
    
    query = {
        "quando_gte": alvo.isoformat(),
        "sentimento": None,  # Todos
        "order": "ts.desc",
        "limit": 500
    }
    
    status, rows = common.sb_select(query)
    if status != 200:
        print(f"Erro ao buscar dados: {rows}")
        return None
    
    csv_lines = []
    csv_lines.append("ts,quando,source,title,link,sentimento")
    
    for r in rows:
        csv_lines.append(f'"{r.get("ts","")}",')
        csv_lines.append(f'"{r.get("quando","")}",')
        csv_lines.append(f'"{r.get("source","")}",')
        csv_lines.append(f'"{r.get("title","").replace(chr(34),chr(39))}",')  # Escapar aspas
        csv_lines.append(f'"{r.get("link","")}",')
        csv_lines.append(f'"{r.get("sentimento","")}"')
    
    csv_content = "\n".join(csv_lines)
    
    if output:
        with open(output, 'w', encoding='utf-8') as f:
            f.write(csv_content)
        print(f"✓ CSV salvo em: {output}")
    
    print(f"✓ CSV gerado: {len(csv_lines)-1} linhas")
    return csv_content

def gerar_json(dias=7):
    """Exporta notícias para JSON"""
    from datetime import datetime, timedelta, timezone
    
    BRT = timezone(timedelta(hours=-3))
    alvo = datetime.now(BRT) - timedelta(days=dias)
    
    query = {
        "quando_gte": alvo.isoformat(),
        "order": "ts.desc",
        "limit": 500
    }
    
    status, rows = common.sb_select(query)
    if status != 200:
        print(f"Erro: {rows}")
        return None
    
    # Resumir por palavra-chave
    summary = {
        "total": len(rows),
        "por_sentimento": {"POSITIVA": 0, "NEGATIVA": 0, "NEUTRA": 0},
        "por_fonte": {},
        "noticias": []
    }
    
    for r in rows:
        s = (r.get("sentimento") or "NEUTRA").upper()
        if s in summary["por_sentimento"]:
            summary["por_sentimento"][s] += 1
        
        src = r.get("source", "Desconhecida")
        summary["por_fonte"][src] = summary["por_fonte"].get(src, 0) + 1
        
        summary["noticias"].append({
            "quando": r.get("quando"),
            "source": src,
            "title": r.get("title"),
            "link": r.get("link"),
            "sentimento": s
        })
    
    print(f"✓ JSON: {summary['total']} notícias | Sentimento: {summary['por_sentimento']}")
    return summary

def testar_conexao():
    """Testa conexão com Supabase"""
    print("\n=== TESTE DE CONEXÃO ===")
    
    status, resp = common.http("GET", f"{common.SUPABASE_URL}/rest/v1/monitored_news?limit=1", 
                               headers={"apikey": common.SUPABASE_KEY})
    
    if status == 200:
        print(f"✓ Conexão OK - Supabase: {common.SUPABASE_URL}")
        return True
    else:
        print(f"✗ Erro conexão: {status} - {resp}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Simulação de teste do sistema de notícias")
    parser.add_argument("--keywords", help="Palavras-chave separadas por ponto e vírgula")
    parser.add_argument("--days", type=int, default=7, help="Dias para análise (default: 7)")
    parser.add_argument("--csv", action="store_true", help="Gerar CSV")
    parser.add_argument("--json", action="store_true", help="Gerar JSON")
    parser.add_argument("--test-conexao", action="store_true", help="Testar conexão Supabase")
    parser.add_argument("--coletar", action="store_true", help="Executar coleta de notícias")
    
    args = parser.parse_args()
    
    if args.test_conexao:
        testar_conexao()
    
    if args.coletar and args.keywords:
        simular_coleta(args.keywords, args.days)
    
    if args.csv:
        gerar_csv(args.days, f"noticias_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
    
    if args.json:
        gerar_json(args.days)

if __name__ == "__main__":
    main()