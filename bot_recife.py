import os
import json
import asyncio
import google.generativeai as genai
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

# Pega as chaves das "Variáveis de Ambiente" do servidor
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN") #8532689413:AAFEmYRLH_BO3ATo9G6pJxQq6iUDOtYaQ0k
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") #AIzaSyCH5VH9S_9XjmxOd9VkhUHXjxgf4clj0Tg
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DB_ID = os.getenv("NOTION_DB_ID")
# --- CONFIGURA O CÉREBRO ---
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')

# --- CÉREBRO (Prompt) ---
SYSTEM_PROMPT = """
Você é um Gerente de Projetos de tecnologia no Recife. 
Receba o relato, entenda gírias (tlgd, visse, boy) e estruture.
Retorne APENAS JSON válido:
{
  "resumo": "Título curto",
  "feito": "O que foi feito",
  "blockers": "Impedimentos (ou null)",
  "proximo": "Próximos passos",
  "status": "Concluído" (ou Travado/Andamento),
  "tags": ["Tag1", "Tag2"]
}
"""

async def processar_com_ia(texto_usuario):
    print(f"🧠 Enviando pra IA: {texto_usuario}") # Debug no terminal
    try:
        response = model.generate_content(f"{SYSTEM_PROMPT}\n\nRELATO: {texto_usuario}")
        texto_limpo = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(texto_limpo)
    except Exception as e:
        print(f"❌ Erro na IA: {e}")
        return None

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name
    texto_entrada = ""

    if update.message.text:
        texto_entrada = update.message.text
        await update.message.reply_text("⏳ Pera aí, tô lendo...")

    # --- PROCESSAMENTO ---
    dados = await processar_com_ia(texto_entrada)
    
    if dados:
        # Mostra no Terminal do seu PC (pra gente ver se funcionou)
        print("\n" + "="*30)
        print(f"✅ SUCESSO! DADOS ESTRUTURADOS DE {user_name.upper()}:")
        print(json.dumps(dados, indent=2, ensure_ascii=False))
        print("="*30 + "\n")

        # Responde no Telegram
        resposta = (
            f"✅ **Entendi, {user_name}!** (Modo Teste)\n\n"
            f"📌 *Tarefa:* {dados['resumo']}\n"
            f"🛠 *Feito:* {dados['feito']}\n"
            f"🚧 *Travas:* {dados['blockers'] if dados['blockers'] else 'Nenhuma'}\n\n"
            f"Simulei que salvei isso no Notion! 🚀"
        )
        await update.message.reply_text(resposta, parse_mode='Markdown')
    else:
        await update.message.reply_text("❌ A IA bugou. Tenta de novo.")

if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    print("🤖 Bot Rodando em MODO TESTE! Manda msg no Telegram...")
    app.run_polling()
