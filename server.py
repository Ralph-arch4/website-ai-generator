from flask import Flask, render_template, request, jsonify, url_for
import uuid
from openai import OpenAI
import os
from dotenv import load_dotenv
import json
import re
import ast
import requests  # Per Stable Diffusion

load_dotenv()
app = Flask(__name__)

# OpenAI per GPT-4o
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Stable Diffusion API Key
STABILITY_API_KEY = os.getenv("STABILITY_API_KEY")
STABILITY_URL = "https://api.stability.ai/v2beta/stable-image/generate/core"

# Directory per salvare immagini
STATIC_IMG_DIR = os.path.join(app.static_folder, "images")
os.makedirs(STATIC_IMG_DIR, exist_ok=True)

sites = {}

# ===== Prompt Style =====
style_instructions_base = """
Usa Google Fonts "Poppins".
Layout responsive con Flexbox.
Bordi arrotondati (border-radius: 10px).
Ombre leggere sugli elementi principali.
Pulsanti con effetto hover animato.
Includi Bootstrap tramite CDN.
"""

structure_instructions = """
Genera un singolo file HTML completo con CSS inline e JavaScript funzionante.
Ogni bottone deve essere collegato a una funzione JavaScript realmente operativa.
Includi il JavaScript direttamente nel file HTML in un tag <script>.
Non includere testo extra o spiegazioni: restituisci SOLO il codice HTML.
Usa semanticamente i tag HTML5 (header, nav, section, article, footer).
Se inserisci immagini, usa SEMPRE segnaposto {{IMG1}}, {{IMG2}}, ecc.
Alla fine dell'HTML aggiungi SEMPRE:
[IMMAGINI_JSON]
{"IMG1": "Descrizione immagine 1", "IMG2": "Descrizione immagine 2"}
Se non ci sono immagini, scrivi:
[IMMAGINI_JSON]
{}
"""

# ===== Parsing sicuro JSON =====
def safe_parse_json(raw_text):
    cleaned = re.sub(r"```[a-zA-Z0-9]*", "", raw_text)
    cleaned = cleaned.replace("```", "").strip()
    try:
        return json.loads(cleaned)
    except:
        try:
            return ast.literal_eval(cleaned)
        except:
            return {}

# ===== Funzione per Stable Diffusion =====
def generate_image_stable_diffusion(prompt, save_path):
    headers = {
        "Authorization": f"Bearer {STABILITY_API_KEY}",
        "Accept": "image/*"  # Diciamo che vogliamo un'immagine
    }

    files = {
        "prompt": (None, prompt),
        "aspect_ratio": (None, "1:1"),
        "output_format": (None, "png")
    }

    response = requests.post(STABILITY_URL, headers=headers, files=files)

    if response.status_code == 200:
        with open(save_path, "wb") as f:
            f.write(response.content)
        return True
    else:
        print("❌ Errore Stable Diffusion:", response.status_code, response.text)
        return False

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/generate", methods=["POST"])
def generate():
    data = request.get_json()
    prompt = data.get("prompt", "")
    image_prompt = data.get("image_prompt", "")
    theme_choice = data.get("theme", "chiaro")

    theme_styles = {
        "chiaro": "Usa una palette chiara con sfondo bianco, testi scuri, tocchi di colore pastello.",
        "scuro": "Usa una palette scura con sfondo quasi nero, testi chiari, accenti neon.",
        "colorato": "Usa una palette vivace con sfondi sfumati e colori brillanti."
    }
    style_instructions = style_instructions_base + "\n" + theme_styles.get(theme_choice, "")

    system_prompt = f"""
    Sei un generatore di siti web.

    [STILE]
    {style_instructions}

    [STRUTTURA]
    {structure_instructions}

    [RICHIESTA UTENTE]
    {prompt}

    [IMMAGINI]
    {image_prompt if image_prompt else "Decidi tu immagini coerenti con il sito."}
    """

    try:
        # 1️⃣ Generazione HTML + JSON immagini con GPT-4o
        response = client.responses.create(
            model="gpt-4o",
            input=[
                {"role": "system", "content": "Genera un sito web completo con immagini e funzionalità reali."},
                {"role": "user", "content": system_prompt}
            ]
        )
        ai_output = response.output_text.strip()

        # Debug GPT
        print("\n=== OUTPUT GPT COMPLETO ===")
        print(ai_output)

        # 2️⃣ Separazione HTML e JSON immagini
        match = re.search(r"\[IMMAGINI_JSON\](.*)", ai_output, re.DOTALL)
        if match:
            html_part = ai_output[:match.start()].strip()
            json_part = match.group(1).strip()
        else:
            html_part = ai_output
            json_part = "{}"

        print("\n=== HTML PRIMA DELLA SOSTITUZIONE ===")
        print(html_part)
        print("\n=== TESTO JSON IMMAGINI ===")
        print(json_part)

        # 3️⃣ Parsing JSON immagini
        image_descriptions = safe_parse_json(json_part)
        if not isinstance(image_descriptions, dict):
            image_descriptions = {}

        print("\n=== DIZIONARIO IMMAGINI ===")
        print(image_descriptions)

        # 4️⃣ Generazione immagini Stable Diffusion
        if not image_descriptions:
            html_part = re.sub(r"\{\{IMG\d+\}\}", "https://via.placeholder.com/1024", html_part)
        else:
            for key, desc in image_descriptions.items():
                try:
                    img_filename = f"{uuid.uuid4()}.png"
                    img_path = os.path.join(STATIC_IMG_DIR, img_filename)
                    if generate_image_stable_diffusion(desc, img_path):
                        local_url = url_for("static", filename=f"images/{img_filename}")
                        html_part = html_part.replace(f"{{{{{key}}}}}", local_url)
                        print(f"✅ Immagine creata: {img_path}")
                    else:
                        html_part = html_part.replace(f"{{{{{key}}}}}", "https://via.placeholder.com/1024")
                except Exception as e:
                    print(f"❌ Errore immagine {key}:", e)
                    html_part = html_part.replace(f"{{{{{key}}}}}", "https://via.placeholder.com/1024")

        generated_html = html_part

    except Exception as e:
        print(f"❌ ERRORE GENERALE: {e}")
        generated_html = f"<html><body><h1>Errore AI:</h1><p>{e}</p></body></html>"

    # 5️⃣ Salvataggio per anteprima
    site_id = str(uuid.uuid4())
    sites[site_id] = generated_html
    return jsonify({"html": generated_html})

if __name__ == "__main__":
    app.run(debug=True)
