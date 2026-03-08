"""
Language detection tool provider.
Returns the language(s) visible on signage at the location.
Uses HF LLM or a static country→language mapping.
"""
from __future__ import annotations
import os
import httpx
from ..models import GeoLocation

COUNTRY_LANGUAGES: dict[str, str] = {
    "FR": "French (Latin script). Typical signage: 'Boulangerie', 'Mairie', 'Sortie'.",
    "DE": "German (Latin script). Typical: 'Ausfahrt', 'Einbahnstrasse', 'Apotheke'.",
    "GB": "English (Latin script). Typical: 'Chemist', 'No Entry', 'High Street'.",
    "IT": "Italian (Latin script). Typical: 'Farmacia', 'Uscita', 'Vietato'.",
    "ES": "Spanish (Latin script). Typical: 'Farmacia', 'Salida', 'Prohibido'.",
    "PT": "Portuguese (Latin script). Typical: 'Farmacia', 'Saida', 'Proibido'.",
    "RU": "Russian (Cyrillic script). Typical: Cyrillic text for pharmacy, exit, street.",
    "JP": "Japanese (Hiragana, Katakana, Kanji scripts mixed). Often vertical signage.",
    "CN": "Simplified Chinese (Hanzi script). Dense character-based signage.",
    "KR": "Korean (Hangul script). Distinctive rounded block characters.",
    "AR": "Arabic script (right-to-left). Decorative calligraphic storefront signs.",
    "SA": "Arabic script (right-to-left). Modern Arabic sans-serif fonts common.",
    "IN": "Hindi/Devanagari + English (bilingual). Regional scripts vary by state.",
    "TH": "Thai script (curved, circular characters) mixed with English.",
    "GR": "Greek (Hellenic script). Distinctive alphabet unlike Latin.",
    "IL": "Hebrew (right-to-left) and Arabic. Latin script also common.",
    "UA": "Ukrainian (Cyrillic). Similar to Russian but distinct characters.",
    "PL": "Polish (Latin with diacritics: a, e, o, z). Distinct pharmacy signs.",
    "SE": "Swedish (Latin). Typical: 'Apotek', 'Utfart', 'Centrum'.",
    "TR": "Turkish (Latin with special chars: s, g, i). Typical: 'Eczane', 'Cikis'.",
    "ID": "Indonesian/Malay (Latin script). Typical: 'Apotek', 'Keluar', 'Jalan'.",
    "VN": "Vietnamese (Latin with tonal diacritics). Dense accent marks visible.",
    "BR": "Portuguese-Brazilian (Latin). Similar to Portugal; 'Farmacia', 'Rua'.",
    "MX": "Spanish (Latin). 'Taqueria', 'Farmacia', 'Calle'.",
    "EG": "Arabic script. Bilingual Arabic/Latin in tourist or urban areas.",
    "NG": "English (Latin) for official signage; Yoruba/Igbo/Hausa in markets.",
    "KE": "English and Swahili (both Latin script). Typical: 'Duka', 'Mtaa'.",
    "ZA": "English + Afrikaans (Latin). Some areas: Zulu/Xhosa/Sotho signage.",
    "ET": "Amharic (Ge'ez/Ethiopic script). Unique angular script unlike any other.",
    "GE": "Georgian script (mkhedruli). Distinctive rounded characters unique to Georgia.",
    "AM": "Armenian script (unique rounded alphabet). Unlike any other script.",
    "MY": "Burmese (Myanmar script). Rounded characters on a baseline.",
    "KH": "Khmer script (Cambodia). Complex rounded subscript characters.",
}

_SYSTEM = (
    "You are a linguistics expert. Given a location, describe the language(s) "
    "visible on street signage in 2-3 sentences. Include: script type, script name, "
    "typical words on pharmacy/exit signs, any bilingual patterns. "
    "Do NOT mention the country or city name."
)


async def resolve(location: GeoLocation, params: dict) -> str:
    hf_key = os.environ.get("HF_API_KEY", "")
    model = os.environ.get("HF_MODEL_ID", "meta-llama/Llama-3.1-8B-Instruct")
    if hf_key:
        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                r = await client.post(
                    f"https://api-inference.huggingface.co/models/{model}/v1/chat/completions",
                    headers={"Authorization": f"Bearer {hf_key}"},
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": _SYSTEM},
                            {"role": "user", "content": (
                                f"Region: {location.region}, "
                                f"country code: {location.country_code}. "
                                "Describe signage language and script."
                            )},
                        ],
                        "max_tokens": 120,
                        "temperature": 0.3,
                    },
                )
                r.raise_for_status()
                return r.json()["choices"][0]["message"]["content"].strip()
        except Exception:
            pass
    return COUNTRY_LANGUAGES.get(
        location.country_code,
        "Latin script is likely, though the specific language is unclear.",
    )
