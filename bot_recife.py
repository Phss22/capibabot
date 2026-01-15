import os
import json
import asyncio
from datetime import date
from threading import Thread
from flask import Flask, request

import google.generativeai as genai
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from notion_client import Client

# --- PEGA AS CHAVES ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DB_ID = os.getenv("NOTION_DB_ID")

# --- CONFIGURAÇÕES ---
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-flash-latest')
notion = Client(auth=NOTION_TOKEN)

# --- PROMPTS ---
PROMPT_ORGANIZADOR = """
Você é um Gerente de Projetos. Analise o texto ou áudio recebido.
Extraia os dados para o Notion. Responda APENAS JSON:
{
  "resumo": "Título curto e formal",
  "feito": "O que foi feito (detalhado)",
  "blockers": "Impedimentos (ou 'Nenhum')",
  "status": "Concluído", 
  "tags": ["Tag1", "Tag2"]
}
Status: "Concluído", "Travado", "Em andamento".
"""

PROMPT_JORNAL = """
Crie um resumo estilo Newsletter diária do time tech. Use emojis.
"""

# --- SERVER FALSO (PRA NÃO DORMIR NO RENDER) ---
server = Flask(__name__)

@server.route('/')
def home():
    return "🤖 Bot Ouvindo!"

def run_server():
    server.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

def keep_alive():
    t = Thread(target=run_server)
    t.start()

# --- FUNÇÕES DO BOT ---

# 1. Função Genérica para falar com a IA (Texto ou Áudio)
async def processar_ia(conteudo, prompt):
    try:
        # Se for string, manda como texto normal
        if isinstance(conteudo, str):
            response = model.generate_content(f"{prompt}\n\nDADOS:\n{conteudo}")
        
        # Se não for string, assume que é um arquivo de áudio processado pelo GenAI
        else:
            response = model.generate_content([prompt, conteudo])
            
        return response.text.replace("```json", "").replace("```", "").strip()
    except Exception as e:
        print(f"❌ Erro na IA: {e}")
        return None

def salvar_notion(dados, usuario):
    try:
        notion.pages.create(
            parent={"database_id": NOTION_DB_ID},
            properties={
                "Nome da Tarefa": {"title": [{"text": {"content": dados['resumo']}}]},
                "Quem": {"rich_text": [{"text": {"content": usuario}}]},
                "O que foi feito": {"rich_text": [{"text": {"content": dados['feito']}}]},
                "Blockers": {"rich_text": [{"text": {"content": dados['blockers']}}]},
                "Status": {"select": {"name": dados['status']}},
                "Tags": {"multi_select": [{"name": tag} for tag in dados['tags']]}
            }
        )
        return True
    except Exception as e:
        print(f"❌ Erro Notion: {e}")
        return False

# 2. Lógica Principal (Lê msg)
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.first_name
    dados_ia = None # Variável pra guardar o que mandar pra IA (Texto ou Arquivo)
    
    # CASO 1: É TEXTO?
    if update.message.text:
        await update.message.reply_text("📝 Lendo texto...")
        dados_ia = update.message.text
        
    # CASO 2: É ÁUDIO/VOZ?
    elif update.message.voice or update.message.audio:
        await update.message.reply_text("🎧 Ouvindo áudio...")
        try:
            # Pega o arquivo do Telegram
            arquivo_id = update.message.voice.file_id if update.message.voice else update.message.audio.file_id
            arquivo_obj = await context.bot.get_file(arquivo_id)
            
            # Baixa temporariamente no servidor
            nome_arquivo = f"audio_{user}.ogg"
            await arquivo_obj.download_to_drive(nome_arquivo)
            
            # Sobe pro Google Gemini (File API)
            print("📤 Subindo áudio pro Google...")
            arquivo_google = genai.upload_file(path=nome_arquivo, mime_type="audio/ogg")
            
            dados_ia = arquivo_google # Agora a entrada é o próprio arquivo
            
            # (Opcional) Limpa o arquivo do disco local depois de subir
            # os.remove(nome_arquivo) -> Pode descomentar se quiser economizar espaço na hora
            
        except Exception as e:
            await update.message.reply_text(f"❌ Erro no áudio: {e}")
            return

    # Se não tiver nada, ignora
    if not dados_ia: return

    # 3. Processa na IA
    res_json = await processar_ia(dados_ia, PROMPT_ORGANIZADOR)
    
    # 4. Salva e Responde
    if res_json:
        try:
            dados = json.loads(res_json)
            if salvar_notion(dados, user):
                await update.message.reply_text(f"✅ **Anotado, {user}!**\n📌 {dados['resumo']}", parse_mode='Markdown')
            else:
                await update.message.reply_text("⚠️ IA entendeu, mas Notion falhou.")
        except:
            await update.message.reply_text("😵 A IA não conseguiu gerar o JSON. Tenta falar mais claro.")

# 3. Lógica do Jornal (Igual antes)
async def gerar_jornal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🗞️ Gerando jornal do dia...")
    try:
        response = notion.databases.query(database_id=NOTION_DB_ID, page_size=50)
        tarefas_hoje = []
        hoje_str = str(date.today())
        
        for page in response['results']:
            data_criacao = page['created_time'][:10]
            if data_criacao == hoje_str:
                props = page['properties']
                # Tratamento de erro caso o campo esteja vazio
                try:
                    titulo = props['Nome da Tarefa']['title'][0]['plain_text']
                    quem = props['Quem']['rich_text'][0]['plain_text']
                    status = props['Status']['select']['name']
                    tarefas_hoje.append(f"- {quem}: {titulo} ({status})")
                except:
                    continue # Pula se faltar dado

        if not tarefas_hoje:
            await update.message.reply_text("💤 Nada feito hoje.")
            return

        texto_para_ia = "\n".join(tarefas_hoje)
        resumo = await processar_ia(texto_para_ia, PROMPT_JORNAL)
        await update.message.reply_text(f"📢 **DIÁRIO DE BORDO**\n\n{resumo}", parse_mode='Markdown')

    except Exception as e:
        print(e)
        await update.message.reply_text("❌ Erro no jornal.")

if __name__ == '__main__':
    keep_alive()
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    # Adiciona suporte a TEXTO e ÁUDIO/VOZ
    app.add_handler(CommandHandler("jornal", gerar_jornal))
    app.add_handler(MessageHandler(filters.TEXT | filters.VOICE | filters.AUDIO, handle_message))
    
    print("🔥 BOT COM ÁUDIO ON!")
    app.run_polling()
