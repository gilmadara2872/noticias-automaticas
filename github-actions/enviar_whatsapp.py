#!/usr/bin/env python3
"""
Envia resumo de notícias via WhatsApp.
Opções:
  1. Twilio API (WhatsApp Business) - produção
  2. Link wa.me (abre WhatsApp Web com texto pré-preenchido) - simples
Uso:
  python enviar_whatsapp.py --csv dados.csv --twilio
  python enviar_whatsapp.py --csv dados.csv --wa-me 62999999999
"""
import os
import sys
import json
import csv
import argparse
from datetime import datetime, timedelta, timezone

BRT = timezone(timedelta(hours=-3))

def formatar_resumo_whatsapp(noticias, dias=7):
    """Formata resumo para WhatsApp"""
    agora = datetime.now(BRT)
    
    # Contar
    total = len(noticias)
    positivas = sum(1 for n in noticias if n.get("sentimento") == "POSITIVA")
    negativas = sum(1 for n in noticias if n.get("sentimento") == "NEGATIVA")
    neutras = sum(1 for n in noticias if n.get("sentimento") == "NEUTRA")
    
    linhas = []
    linhas.append(f"📊 *RESUMO DE NOTÍCIAS - {agora.strftime('%d/%m/%Y')}*")
    linhas.append(f"Período: últimos {dias} dias")
    linhas.append("")
    linhas.append(f"📈 *Total: {total} notícias*")
    linhas.append(f"  ✅ Positivas: {positivas}")
    linhas.append(f"  ❌ Negativas: {negativas}")
    linhas.append(f"  ⚪ Neutras: {neutras}")
    linhas.append("")
    
    # Top 5 notícias
    if noticias:
        linhas.append("📌 *DESTAQUES:*")
        for n in noticias[:5]:
            emoji = "✅" if n.get("sentimento") == "POSITIVA" else "❌" if n.get("sentimento") == "NEGATIVA" else "⚪"
            titulo = n.get("title", "Sem título")[:80]
            fonte = n.get("source", "N/A")
            linhas.append(f"{emoji} {titulo}")
            linhas.append(f"   _{fonte}_")
            linhas.append("")
    
    linhas.append("---")
    linhas.append(f"🤖 Enviado automaticamente às {agora.strftime('%H:%M')}")
    
    return "\n".join(linhas)

def enviar_twilio(texto, para_numero):
    """Envia via Twilio WhatsApp API"""
    try:
        from twilio.rest import Client
    except ImportError:
        print("Erro: twilio não instalado. Rode: pip install twilio")
        return False
    
    account_sid = os.environ.get("TWILIO_SID")
    auth_token = os.environ.get("TWILIO_TOKEN")
    de_numero = os.environ.get("TWILIO_WHATSAPP_NUMBER")  # formato: whatsapp:+14155238886
    
    if not all([account_sid, auth_token, de_numero]):
        print("Erro: Configure TWILIO_SID, TWILIO_TOKEN e TWILIO_WHATSAPP_NUMBER")
        return False
    
    client = Client(account_sid, auth_token)
    
    try:
        message = client.messages.create(
            from_=de_numero,
            body=texto,
            to=f"whatsapp:{para_numero}"
        )
        print(f"✓ Enviado via Twilio: {message.sid}")
        return True
    except Exception as e:
        print(f"✗ Erro Twilio: {e}")
        return False

def gerar_link_wa_me(texto, numero):
    """Gera link wa.me para abrir WhatsApp Web"""
    import urllib.parse
    
    texto_codificado = urllib.parse.quote(texto)
    link = f"https://wa.me/{numero}?text={texto_codificado}"
    
    print(f"\n✓ Link gerado:")
    print(f"  {link}")
    print(f"\n  Abra esse link no navegador para enviar via WhatsApp Web")
    return link

def carregar_csv(caminho):
    """Carrega notícias de CSV"""
    noticias = []
    with open(caminho, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            noticias.append(row)
    return noticias

def main():
    parser = argparse.ArgumentParser(description="Envia resumo via WhatsApp")
    parser.add_argument("--csv", required=True, help="Arquivo CSV com notícias")
    parser.add_argument("--dias", type=int, default=7, help="Período em dias")
    parser.add_argument("--twilio", action="store_true", help="Envia via Twilio API")
    parser.add_argument("--wa-me", help="Gera link wa.me para o número (ex: 5562999999999)")
    parser.add_argument("--para", help="Número destino (formato: 5562999999999)")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.csv):
        print(f"Erro: arquivo {args.csv} não encontrado")
        sys.exit(1)
    
    noticias = carregar_csv(args.csv)
    texto = formatar_resumo_whatsapp(noticias, args.dias)
    
    print("=" * 50)
    print("  RESUMO FORMATADO PARA WHATSAPP")
    print("=" * 50)
    print(texto)
    print("=" * 50)
    
    if args.twilio and args.para:
        enviar_twilio(texto, args.para)
    elif args.wa_me:
        gerar_link_wa_me(texto, args.wa_me)
    else:
        print("\nUse --twilio (com --para) ou --wa-me para enviar")

if __name__ == "__main__":
    main()