import os
import json
import asyncio
from threading import Thread
from flask import Flask, request

import google.generativeai as genai
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

# --- PEGA AS CHAVES ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
# (Tirei o Notion daqui pra não dar erro se faltar a chave)

# --- CONFIGURAÇÕES ---
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-flash-latest')

# --- PROMPT ---
PROMPT_ORGANIZADOR = """
Você é um Gerente de Projetos. Analise o texto ou áudio recebido.
Extraia os dados como se fosse salvar no Notion. Responda APENAS JSON:
{
  "resumo": "Título curto",
  "feito": "Descrição do que foi feito",
  "blockers": "Impedimentos",
  "status": "Concluído", 
  "tags": ["Tag1", "Tag2"]
}
"""

# --- SERVER FALSO (PRA NÃO DORMIR NO RENDER) ---
server = Flask(__name__)

@server.route('/')
def home():
    return "🤖 Bot do Capibaribe (Versão Sem Notion) está VIVO!"

def run_server():
    server.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

def keep_alive():
    t = Thread(target=run_server)
    t.start()

# --- FUNÇÕES DO BOT ---

async def processar_ia(conteudo, prompt):
    try:
        if isinstance(conteudo, str):
            response = model.generate_content(f"{prompt}\n\nDADOS:\n{conteudo}")
        else:
            # Upload do áudio para o Gemini
            response = model.generate_content([prompt, conteudo])
            
        return response.text.replace("```json", "").replace("```", "").strip()
    except Exception as e:
        print(f"❌ Erro na IA: {e}")
        return None

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.first_name
    dados_ia = None
    
    # Lógica de Texto ou Áudio
    if update.message.text:
        await update.message.reply_text("📝 Lendo texto...")
        dados_ia = update.message.text
        
    elif update.message.voice or update.message.audio:
        await update.message.reply_text("🎧 Ouvindo áudio...")
        try:
            arquivo_id = update.message.voice.file_id if update.message.voice else update.message.audio.file_id
            arquivo_obj = await context.bot.get_file(arquivo_id)
            
            nome_arquivo = f"audio_{user}.ogg"
            await arquivo_obj.download_to_drive(nome_arquivo)
            
            # Sobe pro Google
            arquivo_google = genai.upload_file(path=nome_arquivo, mime_type="audio/ogg")
            dados_ia = arquivo_google
            
        except Exception as e:
            await update.message.reply_text(f"❌ Erro no áudio: {e}")
            return

    if not dados_ia: return

    # Processa na IA
    res_json = await processar_ia(dados_ia, PROMPT_ORGANIZADOR)
    
    if res_json:
        try:
            dados = json.loads(res_json)
            
            # --- AQUI É A SIMULAÇÃO ---
            # Em vez de salvar no Notion, a gente só mostra o resultado
            mensagem_final = (
                f"✅ **IA Funcionou, {user}!** (Modo Simulação)\n\n"
                f"📌 **Título:** {dados['resumo']}\n"
                f"🛠 **Feito:** {dados['feito']}\n"
                f"🚦 **Status:** {dados['status']}\n\n"
                f"🚀 *Se o Notion estivesse ligado, isso teria sido salvo!*"
            )
            await update.message.reply_text(mensagem_final, parse_mode='Markdown')
            
        except:
            await update.message.reply_text("😵 A IA não gerou o JSON certo, mas tá viva.")

if __name__ == '__main__':
    keep_alive() # Liga o site falso
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT | filters.VOICE | filters.AUDIO, handle_message))
    print("🔥 BOT ONLINE (MODO SEM NOTION)!")
    app.run_polling()
