import os
import json
import logging
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import List, Dict, Any, Optional

import aiohttp
from bs4 import BeautifulSoup

from telegram import (
    Update,
    BotCommand,
    MenuButtonCommands,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# =========================================================
# CONFIG
# =========================================================

BOT_NAME = "Radar de Investimentos PRO"

TELEGRAM_BOT_TOKEN = (
    os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    or os.getenv("BOT_TOKEN", "").strip()
)

ALERT_CHAT_ID = (
    os.getenv("ALERT_CHAT_ID", "").strip()
    or os.getenv("CHAT_ID", "").strip()
)

CHECK_INTERVAL_MINUTES = int(os.getenv("CHECK_INTERVAL_MINUTES", "5"))

CACHE_FILE = "radar_cache.json"
SETTINGS_FILE = "radar_settings.json"
SENT_ALERTS_FILE = "sent_alerts.json"

# Fallbacks coerentes
DEFAULT_SELIC_ANNUAL = 10.75
DEFAULT_CDI_ANNUAL = 10.65

DEFAULT_SETTINGS = {
    "filters": {
        "daily_min_cdi": 100.0,
        "short_min_cdi": 105.0,
        "isentos_min_cdi": 90.0,
        "score_alert_min": 8.0,
    },
    "sources_enabled": {
        "yubb": True,
        "manual_fallback": True,
    },
    "alert_only_new": True,
    "max_items_per_command": 10,
}

# Fallback local para o radar não ficar “morto”
MANUAL_FALLBACK_OFFERS = [
    {
        "source": "manual_fallback",
        "institution": "Sofisa",
        "product_name": "CDB Sofisa Liquidez Diária",
        "product_type": "CDB",
        "rate_type": "CDI",
        "rate_value": 102.0,
        "liquidity_daily": True,
        "term_days": 1,
        "minimum_investment": 1.0,
        "fgc": True,
        "url": "",
    },
    {
        "source": "manual_fallback",
        "institution": "Master",
        "product_name": "CDB Master 12 meses",
        "product_type": "CDB",
        "rate_type": "CDI",
        "rate_value": 110.0,
        "liquidity_daily": False,
        "term_days": 365,
        "minimum_investment": 1000.0,
        "fgc": True,
        "url": "",
    },
    {
        "source": "manual_fallback",
        "institution": "BS2",
        "product_name": "LCI BS2",
        "product_type": "LCI",
        "rate_type": "CDI",
        "rate_value": 92.0,
        "liquidity_daily": False,
        "term_days": 365,
        "minimum_investment": 1000.0,
        "fgc": True,
        "url": "",
    },
]

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("radar_investimentos_pro")


# =========================================================
# MODELO
# =========================================================

@dataclass
class Investment:
    source: str
    institution: str
    product_name: str
    product_type: str
    rate_type: str
    rate_value: float
    liquidity_daily: bool = False
    term_days: int = 0
    minimum_investment: float = 0.0
    fgc: bool = True
    url: str = ""
    fetched_at: str = field(default_factory=lambda: datetime.now().strftime("%d/%m/%Y %H:%M:%S"))

    gross_annual_return: float = 0.0
    net_annual_return: float = 0.0
    beats_selic: bool = False
    category: str = ""
    score: float = 0.0
    classification: str = ""
    unique_id: str = ""


# =========================================================
# ARQUIVOS JSON
# =========================================================

def load_json_file(path: str, default: Any) -> Any:
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("Falha ao ler %s: %s", path, e)
        return default


def save_json_file(path: str, data: Any) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.exception("Falha ao salvar %s: %s", path, e)


def ensure_files() -> None:
    if not os.path.exists(SETTINGS_FILE):
        save_json_file(SETTINGS_FILE, DEFAULT_SETTINGS)

    if not os.path.exists(CACHE_FILE):
        save_json_file(CACHE_FILE, {
            "last_update": None,
            "benchmark": {},
            "offers": [],
            "buckets": {},
            "source_status": {},
        })

    if not os.path.exists(SENT_ALERTS_FILE):
        save_json_file(SENT_ALERTS_FILE, [])


def load_settings() -> Dict[str, Any]:
    settings = load_json_file(SETTINGS_FILE, DEFAULT_SETTINGS)

    merged = DEFAULT_SETTINGS.copy()
    merged["filters"] = DEFAULT_SETTINGS["filters"].copy()
    merged["filters"].update(settings.get("filters", {}))

    merged["sources_enabled"] = DEFAULT_SETTINGS["sources_enabled"].copy()
    merged["sources_enabled"].update(settings.get("sources_enabled", {}))

    merged["alert_only_new"] = settings.get("alert_only_new", DEFAULT_SETTINGS["alert_only_new"])
    merged["max_items_per_command"] = settings.get("max_items_per_command", DEFAULT_SETTINGS["max_items_per_command"])
    return merged


def load_cache() -> Dict[str, Any]:
    return load_json_file(CACHE_FILE, {
        "last_update": None,
        "benchmark": {},
        "offers": [],
        "buckets": {},
        "source_status": {},
    })


def save_cache(cache_data: Dict[str, Any]) -> None:
    save_json_file(CACHE_FILE, cache_data)


def load_sent_alerts() -> List[str]:
    return load_json_file(SENT_ALERTS_FILE, [])


def save_sent_alerts(alerts: List[str]) -> None:
    save_json_file(SENT_ALERTS_FILE, alerts)


# =========================================================
# CÁLCULOS
# =========================================================

def get_ir_rate(term_days: int) -> float:
    if term_days <= 180:
        return 0.225
    if term_days <= 360:
        return 0.20
    if term_days <= 720:
        return 0.175
    return 0.15


def estimate_gross_annual_return(rate_type: str, rate_value: float, cdi_annual: float) -> float:
    rt = rate_type.upper().strip()

    if rt == "CDI":
        return (rate_value / 100.0) * cdi_annual
    if rt == "PRE":
        return rate_value
    if rt == "IPCA":
        assumed_ipca = 4.5
        return assumed_ipca + rate_value

    return 0.0


def estimate_net_annual_return(
    product_type: str,
    rate_type: str,
    rate_value: float,
    cdi_annual: float,
    term_days: int,
) -> float:
    gross = estimate_gross_annual_return(rate_type, rate_value, cdi_annual)

    if product_type.upper() in ("LCI", "LCA"):
        return gross

    ir = get_ir_rate(term_days if term_days > 0 else 365)
    return gross * (1 - ir)


def classify_category(inv: Investment) -> str:
    pt = inv.product_type.upper().strip()

    if pt in ("LCI", "LCA"):
        return "isentos"
    if pt == "CDB" and inv.liquidity_daily:
        return "diarios"
    if pt == "CDB" and 0 < inv.term_days <= 540:
        return "curtos"

    return "geral"


def build_unique_id(inv: Investment) -> str:
    raw = "|".join([
        inv.source.lower().strip(),
        inv.institution.lower().strip(),
        inv.product_name.lower().strip(),
        inv.product_type.lower().strip(),
        inv.rate_type.lower().strip(),
        f"{inv.rate_value:.4f}",
        str(inv.term_days),
        str(inv.liquidity_daily),
        f"{inv.minimum_investment:.2f}",
    ])
    return str(abs(hash(raw)))


def calculate_score(inv: Investment, selic_annual: float) -> float:
    score = 0.0

    if inv.rate_type.upper() == "CDI":
        if inv.product_type.upper() in ("LCI", "LCA"):
            if inv.rate_value >= 95:
                score += 4.0
            elif inv.rate_value >= 92:
                score += 3.2
            elif inv.rate_value >= 90:
                score += 2.6
            else:
                score += 1.8
        else:
            if inv.rate_value >= 115:
                score += 4.3
            elif inv.rate_value >= 110:
                score += 3.8
            elif inv.rate_value >= 107:
                score += 3.1
            elif inv.rate_value >= 105:
                score += 2.5
            elif inv.rate_value >= 102:
                score += 2.0
            else:
                score += 1.2

    if inv.liquidity_daily:
        score += 1.4

    if inv.term_days > 0:
        if inv.term_days <= 365:
            score += 1.2
        elif inv.term_days <= 720:
            score += 0.8
        else:
            score += 0.4

    if inv.minimum_investment <= 100:
        score += 0.9
    elif inv.minimum_investment <= 1000:
        score += 0.6
    else:
        score += 0.3

    if inv.fgc:
        score += 0.8

    if inv.beats_selic:
        score += 1.6

    if inv.net_annual_return >= selic_annual + 1.0:
        score += 1.2
    elif inv.net_annual_return >= selic_annual:
        score += 0.8

    return round(min(score, 10.0), 1)


def score_to_classification(score: float) -> str:
    if score >= 9.0:
        return "🔴 OPORTUNIDADE IMPERDÍVEL"
    if score >= 8.0:
        return "🟡 OPORTUNIDADE FORTE"
    if score >= 7.0:
        return "🟢 BOA OPORTUNIDADE"
    return "⚪ OPORTUNIDADE PADRÃO"


# =========================================================
# FONTES
# =========================================================

async def fetch_json(session: aiohttp.ClientSession, url: str, timeout: int = 20) -> Any:
    async with session.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"}) as resp:
        resp.raise_for_status()
        return await resp.json()


async def fetch_text(session: aiohttp.ClientSession, url: str, timeout: int = 20) -> str:
    async with session.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"}) as resp:
        resp.raise_for_status()
        return await resp.text()


def sanitize_benchmark(selic: float, cdi: float) -> Dict[str, float]:
    """
    Evita benchmark estranho vindo de API.
    Se vier algo fora de uma faixa plausível, usa fallback.
    """
    if not (5.0 <= selic <= 20.0):
        selic = DEFAULT_SELIC_ANNUAL

    if not (4.5 <= cdi <= 19.5):
        cdi = DEFAULT_CDI_ANNUAL

    # Mantém CDI levemente abaixo da Selic, se necessário
    if cdi > selic:
        cdi = round(max(selic - 0.10, 0.0), 2)

    return {
        "selic_annual": round(selic, 2),
        "cdi_annual": round(cdi, 2),
    }


async def get_selic_benchmark(session: aiohttp.ClientSession) -> Dict[str, float]:
    """
    Busca benchmark com fallback seguro.
    """
    selic = DEFAULT_SELIC_ANNUAL
    cdi = DEFAULT_CDI_ANNUAL

    try:
        url = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados/ultimos/1?formato=json"
        data = await fetch_json(session, url)
        if data and isinstance(data, list):
            valor = str(data[0].get("valor", "")).replace(",", ".")
            selic_api = float(valor)

            # Só aceita se fizer sentido
            if 5.0 <= selic_api <= 20.0:
                selic = selic_api
    except Exception as e:
        logger.warning("Falha ao buscar Selic oficial. Usando fallback: %s", e)

    # CDI aproximado
    cdi = round(max(selic - 0.10, 0.0), 2)
    return sanitize_benchmark(selic, cdi)


async def collect_manual_fallback() -> List[Investment]:
    investments = []
    for item in MANUAL_FALLBACK_OFFERS:
        investments.append(
            Investment(
                source=item["source"],
                institution=item["institution"],
                product_name=item["product_name"],
                product_type=item["product_type"],
                rate_type=item["rate_type"],
                rate_value=float(item["rate_value"]),
                liquidity_daily=bool(item.get("liquidity_daily", False)),
                term_days=int(item.get("term_days", 0)),
                minimum_investment=float(item.get("minimum_investment", 0)),
                fgc=bool(item.get("fgc", True)),
                url=item.get("url", ""),
            )
        )
    return investments


async def collect_yubb(session: aiohttp.ClientSession) -> List[Investment]:
    """
    Coletor best-effort.
    Ainda pode precisar de ajuste fino futuro.
    """
    results: List[Investment] = []

    candidate_urls = [
        "https://yubb.com.br/investimentos/renda-fixa",
        "https://yubb.com.br",
    ]

    for url in candidate_urls:
        try:
            html = await fetch_text(session, url, timeout=20)
            soup = BeautifulSoup(html, "html.parser")

            page_text = soup.get_text(" ", strip=True).lower()
            if not any(x in page_text for x in ["cdb", "lci", "lca"]):
                continue

            blocks = soup.find_all(["div", "article", "section"])
            found = 0

            for block in blocks:
                text = block.get_text(" ", strip=True)
                low = text.lower()

                if not any(x in low for x in ["cdb", "lci", "lca"]):
                    continue

                if "lci" in low:
                    product_type = "LCI"
                elif "lca" in low:
                    product_type = "LCA"
                elif "cdb" in low:
                    product_type = "CDB"
                else:
                    continue

                rate_value = None
                for token in text.replace("%", " % ").split():
                    t = token.replace(",", ".")
                    try:
                        num = float(t)
                        if 70 <= num <= 200:
                            rate_value = num
                            break
                    except Exception:
                        pass

                if rate_value is None:
                    continue

                liquidity_daily = "liquidez diária" in low or "liquidez diaria" in low
                term_days = 365

                if "90 dias" in low:
                    term_days = 90
                elif "180 dias" in low:
                    term_days = 180
                elif "12 meses" in low or "1 ano" in low:
                    term_days = 365
                elif "24 meses" in low or "2 anos" in low:
                    term_days = 730

                results.append(
                    Investment(
                        source="yubb",
                        institution="Yubb",
                        product_name=f"{product_type} encontrado no Yubb",
                        product_type=product_type,
                        rate_type="CDI",
                        rate_value=float(rate_value),
                        liquidity_daily=liquidity_daily,
                        term_days=term_days,
                        minimum_investment=1000.0,
                        fgc=True,
                        url=url,
                    )
                )

                found += 1
                if found >= 15:
                    break

            if results:
                break

        except Exception as e:
            logger.warning("Falha ao coletar Yubb em %s: %s", url, e)

    return results


# =========================================================
# PROCESSAMENTO
# =========================================================

def enrich_investments(investments: List[Investment], benchmark: Dict[str, float]) -> List[Investment]:
    selic_annual = benchmark["selic_annual"]
    cdi_annual = benchmark["cdi_annual"]

    for inv in investments:
        inv.category = classify_category(inv)
        inv.gross_annual_return = round(
            estimate_gross_annual_return(inv.rate_type, inv.rate_value, cdi_annual), 2
        )
        inv.net_annual_return = round(
            estimate_net_annual_return(inv.product_type, inv.rate_type, inv.rate_value, cdi_annual, inv.term_days), 2
        )
        inv.beats_selic = inv.net_annual_return > selic_annual
        inv.unique_id = build_unique_id(inv)
        inv.score = calculate_score(inv, selic_annual)
        inv.classification = score_to_classification(inv.score)

    return investments


def deduplicate_investments(investments: List[Investment]) -> List[Investment]:
    seen = set()
    unique = []

    for inv in investments:
        if inv.unique_id not in seen:
            seen.add(inv.unique_id)
            unique.append(inv)

    return unique


def apply_filters(investments: List[Investment], settings: Dict[str, Any]) -> Dict[str, List[Investment]]:
    filters_cfg = settings["filters"]

    diarios = [
        i for i in investments
        if i.category == "diarios"
        and i.rate_type.upper() == "CDI"
        and i.rate_value >= filters_cfg["daily_min_cdi"]
    ]

    curtos = [
        i for i in investments
        if i.category == "curtos"
        and i.rate_type.upper() == "CDI"
        and i.rate_value >= filters_cfg["short_min_cdi"]
    ]

    isentos = [
        i for i in investments
        if i.category == "isentos"
        and i.rate_type.upper() == "CDI"
        and i.rate_value >= filters_cfg["isentos_min_cdi"]
    ]

    selicplus = [i for i in investments if i.beats_selic]

    ranking = sorted(investments, key=lambda x: (x.score, x.net_annual_return), reverse=True)
    top10 = ranking[:10]

    return {
        "diarios": sorted(diarios, key=lambda x: (x.score, x.rate_value), reverse=True),
        "curtos": sorted(curtos, key=lambda x: (x.score, x.rate_value), reverse=True),
        "isentos": sorted(isentos, key=lambda x: (x.score, x.rate_value), reverse=True),
        "selicplus": sorted(selicplus, key=lambda x: (x.score, x.net_annual_return), reverse=True),
        "ranking": ranking,
        "top10": top10,
    }


async def collect_all_sources(settings: Dict[str, Any]) -> Dict[str, Any]:
    benchmark = {
        "selic_annual": DEFAULT_SELIC_ANNUAL,
        "cdi_annual": DEFAULT_CDI_ANNUAL,
    }

    all_investments: List[Investment] = []
    source_status: Dict[str, int] = {}

    timeout = aiohttp.ClientTimeout(total=40)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        benchmark = await get_selic_benchmark(session)

        if settings["sources_enabled"].get("yubb", False):
            try:
                yubb_items = await collect_yubb(session)
                all_investments.extend(yubb_items)
                source_status["Yubb"] = len(yubb_items)
            except Exception as e:
                logger.warning("Erro no coletor Yubb: %s", e)
                source_status["Yubb"] = 0
        else:
            source_status["Yubb"] = 0

    if settings["sources_enabled"].get("manual_fallback", False):
        try:
            manual_items = await collect_manual_fallback()
            all_investments.extend(manual_items)
            source_status["Fallback manual"] = len(manual_items)
        except Exception as e:
            logger.warning("Erro no fallback manual: %s", e)
            source_status["Fallback manual"] = 0
    else:
        source_status["Fallback manual"] = 0

    all_investments = enrich_investments(all_investments, benchmark)
    all_investments = deduplicate_investments(all_investments)

    buckets = apply_filters(all_investments, settings)

    cache_data = {
        "last_update": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        "benchmark": benchmark,
        "offers": [asdict(x) for x in all_investments],
        "buckets": {k: [asdict(i) for i in v] for k, v in buckets.items()},
        "source_status": source_status,
    }

    save_cache(cache_data)
    return cache_data


# =========================================================
# FORMATAÇÃO
# =========================================================

def money_br(value: float) -> str:
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def format_rate(inv: Dict[str, Any]) -> str:
    rt = inv.get("rate_type", "CDI").upper()
    rv = float(inv.get("rate_value", 0))

    if rt == "CDI":
        return f"{rv:.2f}% do CDI"
    if rt == "PRE":
        return f"{rv:.2f}% a.a."
    if rt == "IPCA":
        return f"IPCA + {rv:.2f}% a.a."
    return f"{rv:.2f}"


def format_item(inv: Dict[str, Any], show_url: bool = False, rank_position: Optional[int] = None) -> str:
    if rank_position is None:
        prefix = ""
    elif 1 <= rank_position <= 9:
        prefix = f"{rank_position}️⃣ "
    else:
        prefix = f"{rank_position}. "

    lines = [
        f"{prefix}<b>{inv.get('product_name', 'Produto')}</b>",
        f"🏦 Instituição: {inv.get('institution', '-')}",
        f"📦 Tipo: {inv.get('product_type', '-')}",
        f"💹 Taxa: {format_rate(inv)}",
        f"📅 Prazo: {inv.get('term_days', 0)} dias",
        f"💵 Mínimo: {money_br(float(inv.get('minimum_investment', 0)))}",
        f"💧 Liquidez diária: {'Sim' if inv.get('liquidity_daily') else 'Não'}",
        f"🧾 Retorno bruto estimado: {float(inv.get('gross_annual_return', 0)):.2f}% a.a.",
        f"💰 Retorno líquido estimado: {float(inv.get('net_annual_return', 0)):.2f}% a.a.",
        f"🏦 FGC: {'Sim' if inv.get('fgc') else 'Não'}",
        f"📊 Score: {float(inv.get('score', 0)):.1f}",
        f"{inv.get('classification', '⚪ OPORTUNIDADE PADRÃO')}",
        f"{'✅ Melhor que o Tesouro Selic' if inv.get('beats_selic') else '➖ Não supera o Tesouro Selic'}",
        f"🌐 Fonte: {inv.get('source', '-')}",
    ]

    url = str(inv.get("url", "")).strip()
    if show_url and url:
        lines.append(f"🔗 <a href=\"{url}\">Abrir fonte</a>")

    return "\n".join(lines)


def format_empty_message(title: str) -> str:
    return f"{title}\n\nNenhuma oportunidade encontrada na fonte monitorada agora."


def render_list(title: str, items: List[Dict[str, Any]], max_items: int = 10) -> str:
    if not items:
        return format_empty_message(title)

    lines = [title, ""]
    for idx, item in enumerate(items[:max_items], start=1):
        lines.append(format_item(item, show_url=True, rank_position=idx))
        lines.append("")
    return "\n".join(lines).strip()


def menu_message() -> str:
    return (
        f"💰 <b>{BOT_NAME}</b>\n\n"
        "/menu - abrir menu\n"
        "/status - status do radar\n"
        "/ranking - ranking geral de oportunidades\n"
        "/top10 - top 10 oportunidades\n"
        "/diarios - CDBs de liquidez diária\n"
        "/curtos - CDBs de prazo curto\n"
        "/isentos - LCI / LCA\n"
        "/benchmark - benchmark Tesouro Selic\n"
        "/selicplus - produtos melhores que Selic\n"
        "/atualizar - forçar atualização do radar\n"
    )


def status_message(cache_data: Dict[str, Any]) -> str:
    buckets = cache_data.get("buckets", {})
    benchmark = cache_data.get("benchmark", {})
    source_status = cache_data.get("source_status", {})
    last_update = cache_data.get("last_update", "Nunca")

    source_lines = []
    for name, count in source_status.items():
        source_lines.append(f"✔ {name}: {count}")

    if not source_lines:
        source_lines = ["✔ Nenhuma fonte registrada"]

    return (
        f"🟢 <b>{BOT_NAME} online</b>\n\n"
        f"Última atualização: {last_update}\n"
        f"Diários no cache: {len(buckets.get('diarios', []))}\n"
        f"Curtos no cache: {len(buckets.get('curtos', []))}\n"
        f"Isentos no cache: {len(buckets.get('isentos', []))}\n"
        f"Melhores que Selic: {len(buckets.get('selicplus', []))}\n"
        f"Ranking total: {len(buckets.get('ranking', []))}\n\n"
        f"Benchmark Selic aproximado: {benchmark.get('selic_annual', DEFAULT_SELIC_ANNUAL):.2f}%\n"
        f"CDI aproximado: {benchmark.get('cdi_annual', DEFAULT_CDI_ANNUAL):.2f}%\n\n"
        "Fontes monitoradas:\n"
        + "\n".join(source_lines)
    )


def benchmark_message(cache_data: Dict[str, Any]) -> str:
    bench = cache_data.get("benchmark", {})
    selic = float(bench.get("selic_annual", DEFAULT_SELIC_ANNUAL))
    cdi = float(bench.get("cdi_annual", DEFAULT_CDI_ANNUAL))

    return (
        "🏦 <b>Benchmark</b>\n\n"
        "Tesouro Selic\n\n"
        f"Taxa aproximada: {selic:.2f}%\n"
        f"CDI aproximado: {cdi:.2f}%"
    )


def build_main_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton("📋 Menu"), KeyboardButton("📊 Status")],
        [KeyboardButton("🏆 Ranking"), KeyboardButton("🔝 Top 10")],
        [KeyboardButton("💧 Diários"), KeyboardButton("⏱ Curtos")],
        [KeyboardButton("🟢 Isentos"), KeyboardButton("🏦 Benchmark")],
        [KeyboardButton("🚨 Selic Plus"), KeyboardButton("🔄 Atualizar")],
    ]
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True,
    )


# =========================================================
# ALERTAS
# =========================================================

async def send_new_alerts(application: Application, cache_data: Dict[str, Any]) -> None:
    if not ALERT_CHAT_ID:
        logger.info("CHAT_ID / ALERT_CHAT_ID não configurado. Alertas automáticos desativados.")
        return

    settings = load_settings()
    min_score = float(settings["filters"]["score_alert_min"])
    alert_only_new = bool(settings.get("alert_only_new", True))

    sent_alerts = set(load_sent_alerts())
    ranking = cache_data.get("buckets", {}).get("ranking", [])
    candidates = [x for x in ranking if float(x.get("score", 0)) >= min_score]

    updated_sent = set(sent_alerts)

    for inv in candidates[:5]:
        uid = str(inv.get("unique_id", ""))
        if alert_only_new and uid in sent_alerts:
            continue

        msg = "🚨 <b>OPORTUNIDADE DETECTADA</b>\n\n" + format_item(inv, show_url=True)

        try:
            await application.bot.send_message(
                chat_id=ALERT_CHAT_ID,
                text=msg,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
            if uid:
                updated_sent.add(uid)
        except Exception as e:
            logger.exception("Erro ao enviar alerta: %s", e)

    save_sent_alerts(sorted(updated_sent))


# =========================================================
# COMANDOS
# =========================================================

async def setup_commands(app: Application) -> None:
    commands = [
        BotCommand("menu", "Abrir menu do radar"),
        BotCommand("status", "Status do radar"),
        BotCommand("ranking", "Ranking de oportunidades"),
        BotCommand("top10", "Top 10 oportunidades"),
        BotCommand("diarios", "CDB liquidez diária"),
        BotCommand("curtos", "CDB prazo curto"),
        BotCommand("isentos", "LCI / LCA"),
        BotCommand("benchmark", "Tesouro Selic"),
        BotCommand("selicplus", "Melhores que Selic"),
        BotCommand("atualizar", "Forçar atualização do radar"),
    ]
    await app.bot.set_my_commands(commands)
    await app.bot.set_chat_menu_button(menu_button=MenuButtonCommands())


async def send_with_keyboard(update: Update, text: str) -> None:
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
        reply_markup=build_main_keyboard(),
    )


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Sem duplicar o nome do bot
    await send_with_keyboard(update, menu_message())


async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_with_keyboard(update, menu_message())


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cache_data = load_cache()
    await send_with_keyboard(update, status_message(cache_data))


async def cmd_benchmark(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cache_data = load_cache()
    await send_with_keyboard(update, benchmark_message(cache_data))


async def cmd_ranking(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cache_data = load_cache()
    items = cache_data.get("buckets", {}).get("ranking", [])
    msg = render_list("🏆 <b>Ranking de oportunidades</b>", items, max_items=load_settings()["max_items_per_command"])
    await send_with_keyboard(update, msg)


async def cmd_top10(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cache_data = load_cache()
    items = cache_data.get("buckets", {}).get("top10", [])
    msg = render_list("🔝 <b>Top 10 oportunidades</b>", items, max_items=10)
    await send_with_keyboard(update, msg)


async def cmd_diarios(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cache_data = load_cache()
    items = cache_data.get("buckets", {}).get("diarios", [])
    msg = render_list("💧 <b>CDBs de liquidez diária</b>", items, max_items=load_settings()["max_items_per_command"])
    await send_with_keyboard(update, msg)


async def cmd_curtos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cache_data = load_cache()
    items = cache_data.get("buckets", {}).get("curtos", [])
    msg = render_list("⏱ <b>CDBs de prazo curto</b>", items, max_items=load_settings()["max_items_per_command"])
    await send_with_keyboard(update, msg)


async def cmd_isentos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cache_data = load_cache()
    items = cache_data.get("buckets", {}).get("isentos", [])
    msg = render_list("🟢 <b>LCI / LCA</b>", items, max_items=load_settings()["max_items_per_command"])
    await send_with_keyboard(update, msg)


async def cmd_selicplus(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cache_data = load_cache()
    items = cache_data.get("buckets", {}).get("selicplus", [])
    msg = render_list("🚨 <b>Melhores que o Tesouro Selic</b>", items, max_items=load_settings()["max_items_per_command"])
    await send_with_keyboard(update, msg)


async def cmd_atualizar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_with_keyboard(update, "🔄 Atualizando radar...")
    try:
        cache_data = await collect_all_sources(load_settings())
        await send_new_alerts(context.application, cache_data)
        await send_with_keyboard(update, "✅ Radar atualizado com sucesso.")
    except Exception as e:
        logger.exception("Erro na atualização manual: %s", e)
        await send_with_keyboard(update, f"❌ Erro ao atualizar o radar: {e}")


# =========================================================
# BOTÕES DE TEXTO
# =========================================================

async def handle_text_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip().lower()

    if text == "📋 menu":
        await cmd_menu(update, context)
    elif text == "📊 status":
        await cmd_status(update, context)
    elif text == "🏆 ranking":
        await cmd_ranking(update, context)
    elif text == "🔝 top 10":
        await cmd_top10(update, context)
    elif text == "💧 diários":
        await cmd_diarios(update, context)
    elif text == "⏱ curtos":
        await cmd_curtos(update, context)
    elif text == "🟢 isentos":
        await cmd_isentos(update, context)
    elif text == "🏦 benchmark":
        await cmd_benchmark(update, context)
    elif text == "🚨 selic plus":
        await cmd_selicplus(update, context)
    elif text == "🔄 atualizar":
        await cmd_atualizar(update, context)


# =========================================================
# JOB
# =========================================================

async def radar_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        logger.info("Executando radar_job...")
        cache_data = await collect_all_sources(load_settings())
        await send_new_alerts(context.application, cache_data)
        logger.info("radar_job concluído.")
    except Exception as e:
        logger.exception("Erro no radar_job: %s", e)


# =========================================================
# STARTUP
# =========================================================

async def on_startup(app: Application) -> None:
    logger.info("Inicializando bot...")
    await setup_commands(app)

    try:
        cache_data = await collect_all_sources(load_settings())
        await send_new_alerts(app, cache_data)
    except Exception as e:
        logger.exception("Falha na carga inicial: %s", e)


# =========================================================
# MAIN
# =========================================================

def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("Defina TELEGRAM_BOT_TOKEN ou BOT_TOKEN nas variáveis do Railway.")

    ensure_files()

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.post_init = on_startup

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("ranking", cmd_ranking))
    app.add_handler(CommandHandler("top10", cmd_top10))
    app.add_handler(CommandHandler("diarios", cmd_diarios))
    app.add_handler(CommandHandler("curtos", cmd_curtos))
    app.add_handler(CommandHandler("isentos", cmd_isentos))
    app.add_handler(CommandHandler("benchmark", cmd_benchmark))
    app.add_handler(CommandHandler("selicplus", cmd_selicplus))
    app.add_handler(CommandHandler("atualizar", cmd_atualizar))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_buttons))

    if app.job_queue is not None:
        app.job_queue.run_repeating(
            radar_job,
            interval=CHECK_INTERVAL_MINUTES * 60,
            first=15,
            name="radar_job",
        )
    else:
        logger.warning("JobQueue não disponível. O radar automático ficará desativado.")

    logger.info("%s iniciado. Intervalo do radar: %s minutos.", BOT_NAME, CHECK_INTERVAL_MINUTES)
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
