import os
import io
import shutil
import asyncio
import subprocess
from pathlib import Path
from tg_bot.config import POLZA_API_KEY, AI_BASE_URL, CLAUDE_MODEL, GEMINI_API_KEY, MATERIALS_DIR
from tg_bot.engine.prompts import get_system_prompt_for_role

async def transcribe_audio_bytes(audio_bytes: bytes, filename: str = "audio.ogg") -> str:
    """Transcribes audio using Whisper / Polza API."""
    if not POLZA_API_KEY:
        return "Ошибка: API ключ не настроен для транскрибации."
        
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=POLZA_API_KEY, base_url=AI_BASE_URL)
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = filename
        transcription = await client.audio.transcriptions.create(
            model="openai/whisper-1",
            file=audio_file
        )
        return transcription.text
    except Exception as e:
        return f"Ошибка распознавания аудио: {e}"

def find_agy_binary() -> str | None:
    """Finds the local agy CLI binary path."""
    which_agy = shutil.which("agy")
    if which_agy:
        return which_agy
    local_paths = [
        Path("/usr/local/bin/agy"),
        Path.home() / ".local" / "bin" / "agy",
        Path("/root/.local/bin/agy"),
        Path("/opt/antigravity/bin/agy")
    ]
    for p in local_paths:
        if p.exists() and os.access(p, os.X_OK):
            return str(p)
    return None

async def run_agy_cli(system_instruction: str, user_prompt: str) -> str | None:
    """Executes prompt via agy CLI."""
    agy_path = find_agy_binary()
    if not agy_path:
        return None

    full_cli_prompt = f"{system_instruction}\n\nПользовательский запрос:\n{user_prompt}"
    
    try:
        proc = await asyncio.create_subprocess_exec(
            agy_path,
            "-p",
            full_cli_prompt,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=180.0)
        
        if proc.returncode == 0 and stdout:
            result = stdout.decode("utf-8", errors="replace").strip()
            if result:
                return result
    except Exception as e:
        print(f"[AGY CLI Error]: {e}")
    return None

async def run_agent_task(
    role: str,
    user_prompt: str,
    attachment_text: str = "",
    image_bytes: bytes | None = None,
    audio_bytes: bytes | None = None,
    mime_type: str | None = None
) -> tuple[str, str]:
    """
    Executes an agent task primarily via AGY CLI / Google Antigravity Agent runtime,
    with automatic fallbacks. Returns (response_text, model_name).
    """
    system_instruction = get_system_prompt_for_role(role)
    
    # If audio is attached, transcribe it first
    if audio_bytes:
        transcribed_text = await transcribe_audio_bytes(audio_bytes, filename=f"voice.{'mp3' if 'mp3' in (mime_type or '') else 'ogg'}")
        attachment_text = (attachment_text + "\n\n" if attachment_text else "") + f"[РАСШИФРОВКА АУДИОЗАПИСИ]:\n{transcribed_text}"

    # Context injection from project materials
    context_intro = ""
    if role in ["content", "hooks", "fakt-check"]:
        if MATERIALS_DIR.exists():
            files = sorted(list(MATERIALS_DIR.glob("*.*")), key=os.path.getmtime, reverse=True)[:3]
            file_names = [f.name for f in files]
            if file_names:
                context_intro = f"\n[Материалы проекта: {', '.join(file_names)}]\n"

    full_prompt = f"{context_intro}\n{user_prompt}".strip()
    if attachment_text:
        full_prompt += f"\n\n--- ПРИКРЕПЛЕННЫЙ МАТЕРИАЛ ---\n{attachment_text}"

    # 1. PRIMARY: AGY CLI (Google Antigravity CLI)
    agy_res = await run_agy_cli(system_instruction, full_prompt)
    if agy_res:
        return agy_res, "Antigravity CLI (agy / Gemini)"

    # 2. SECONDARY: Google Antigravity SDK
    try:
        from google.antigravity import Agent, LocalAgentConfig, CapabilitiesConfig
        config = LocalAgentConfig(
            system_instructions=system_instruction,
            capabilities=CapabilitiesConfig()
        )
        async with Agent(config) as agent:
            response = await agent.chat(full_prompt)
            full_text = ""
            async for token in response:
                full_text += str(token)
            if full_text.strip():
                return full_text.strip(), "Google Antigravity SDK"
    except Exception as agy_err:
        pass

    # 3. FALLBACK: Polza AI / Claude Sonnet
    if POLZA_API_KEY:
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=POLZA_API_KEY, base_url=AI_BASE_URL)
            messages = [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": full_prompt}
            ]
            if image_bytes and mime_type:
                import base64
                b64_img = base64.b64encode(image_bytes).decode("utf-8")
                messages = [
                    {"role": "system", "content": system_instruction},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": full_prompt},
                            {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64_img}"}}
                        ]
                    }
                ]
            res = await client.chat.completions.create(
                model=CLAUDE_MODEL,
                messages=messages,
                temperature=0.6 if role in ["content", "hooks"] else 0.2,
                max_tokens=4000
            )
            if res.choices and res.choices[0].message.content:
                return res.choices[0].message.content.strip(), f"Claude 3.5 Sonnet (Polza AI)"
        except Exception as polza_err:
            print(f"[Polza AI error]: {polza_err}")

    # 4. FALLBACK: Gemini
    if GEMINI_API_KEY:
        try:
            from google import genai
            client = genai.Client(api_key=GEMINI_API_KEY)
            res = await asyncio.to_thread(
                client.models.generate_content,
                model="gemini-2.5-flash",
                contents=[system_instruction, full_prompt]
            )
            if res and res.text:
                return res.text.strip(), "Gemini 2.5 Flash"
        except Exception as gemini_err:
            print(f"[Gemini error]: {gemini_err}")

    return "❌ Ошибка: не удалось получить ответ от AI-агента.", "Error"
