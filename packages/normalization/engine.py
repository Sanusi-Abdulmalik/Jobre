from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any

import bleach
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

from packages.common.security import canonicalize_url, sha256_hex


class EmploymentType(StrEnum):
    FULL_TIME = "FULL_TIME"
    PART_TIME = "PART_TIME"
    CONTRACT = "CONTRACT"
    TEMPORARY = "TEMPORARY"
    INTERNSHIP = "INTERNSHIP"
    APPRENTICESHIP = "APPRENTICESHIP"
    UNKNOWN = "UNKNOWN"


class WorkplaceType(StrEnum):
    REMOTE = "REMOTE"
    HYBRID = "HYBRID"
    ON_SITE = "ON_SITE"
    UNKNOWN = "UNKNOWN"


class SalaryPeriod(StrEnum):
    YEAR = "YEAR"
    MONTH = "MONTH"
    WEEK = "WEEK"
    DAY = "DAY"
    HOUR = "HOUR"


ALLOWED_HTML_TAGS = [
    "p",
    "br",
    "ul",
    "ol",
    "li",
    "strong",
    "b",
    "em",
    "i",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "blockquote",
    "code",
    "pre",
    "a",
]
ALLOWED_HTML_ATTRS = {"a": ["href", "title", "rel"]}

LEGAL_ENTITY_SUFFIX_RE = re.compile(
    r"\b(?:inc\.?|incorporated|llc|l\.l\.c\.?|ltd\.?|limited|corp\.?|corporation|"
    r"gmbh|ag|plc|s\.a\.?|b\.v\.?|pvt\.?\s*ltd\.?|co\.?|company|group|holdings)\b\.?",
    re.IGNORECASE,
)

US_STATES: dict[str, str] = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa",
    "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire",
    "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York", "NC": "North Carolina",
    "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
    "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee",
    "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
    "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia",
}
US_STATE_NAMES_LOWER = {v.lower(): (k, v) for k, v in US_STATES.items()}

CA_PROVINCES: dict[str, str] = {
    "ON": "Ontario", "BC": "British Columbia", "QC": "Quebec", "AB": "Alberta",
    "MB": "Manitoba", "SK": "Saskatchewan", "NS": "Nova Scotia", "NB": "New Brunswick",
}

COUNTRY_ALIASES: dict[str, tuple[str, str]] = {
    "us": ("United States", "US"),
    "usa": ("United States", "US"),
    "u.s.": ("United States", "US"),
    "u.s.a.": ("United States", "US"),
    "united states": ("United States", "US"),
    "united states of america": ("United States", "US"),
    "uk": ("United Kingdom", "GB"),
    "united kingdom": ("United Kingdom", "GB"),
    "great britain": ("United Kingdom", "GB"),
    "england": ("United Kingdom", "GB"),
    "canada": ("Canada", "CA"),
    "germany": ("Germany", "DE"),
    "deutschland": ("Germany", "DE"),
    "france": ("France", "FR"),
    "netherlands": ("Netherlands", "NL"),
    "nederland": ("Netherlands", "NL"),
    "spain": ("Spain", "ES"),
    "italy": ("Italy", "IT"),
    "sweden": ("Sweden", "SE"),
    "switzerland": ("Switzerland", "CH"),
    "austria": ("Austria", "AT"),
    "ireland": ("Ireland", "IE"),
    "poland": ("Poland", "PL"),
    "portugal": ("Portugal", "PT"),
    "india": ("India", "IN"),
    "singapore": ("Singapore", "SG"),
    "australia": ("Australia", "AU"),
    "japan": ("Japan", "JP"),
    "brazil": ("Brazil", "BR"),
    "mexico": ("Mexico", "MX"),
    "nigeria": ("Nigeria", "NG"),
    "kenya": ("Kenya", "KE"),
    "south africa": ("South Africa", "ZA"),
    "ethiopia": ("Ethiopia", "ET"),
    "uae": ("United Arab Emirates", "AE"),
    "united arab emirates": ("United Arab Emirates", "AE"),
    "israel": ("Israel", "IL"),
}

KNOWN_CITY_COUNTRIES: dict[str, tuple[str, str | None, str, str]] = {
    "london": ("London", "England", "United Kingdom", "GB"),
    "berlin": ("Berlin", "Berlin", "Germany", "DE"),
    "munich": ("Munich", "Bavaria", "Germany", "DE"),
    "münchen": ("Munich", "Bavaria", "Germany", "DE"),
    "paris": ("Paris", "Île-de-France", "France", "FR"),
    "amsterdam": ("Amsterdam", "North Holland", "Netherlands", "NL"),
    "dublin": ("Dublin", "Leinster", "Ireland", "IE"),
    "toronto": ("Toronto", "Ontario", "Canada", "CA"),
    "vancouver": ("Vancouver", "British Columbia", "Canada", "CA"),
    "montreal": ("Montreal", "Quebec", "Canada", "CA"),
    "montréal": ("Montreal", "Quebec", "Canada", "CA"),
    "bengaluru": ("Bengaluru", "Karnataka", "India", "IN"),
    "bangalore": ("Bengaluru", "Karnataka", "India", "IN"),
    "mumbai": ("Mumbai", "Maharashtra", "India", "IN"),
    "hyderabad": ("Hyderabad", "Telangana", "India", "IN"),
    "singapore": ("Singapore", None, "Singapore", "SG"),
    "tokyo": ("Tokyo", "Tokyo", "Japan", "JP"),
    "sydney": ("Sydney", "New South Wales", "Australia", "AU"),
    "lagos": ("Lagos", "Lagos", "Nigeria", "NG"),
    "nairobi": ("Nairobi", "Nairobi", "Kenya", "KE"),
    "addis ababa": ("Addis Ababa", "Addis Ababa", "Ethiopia", "ET"),
    "san francisco": ("San Francisco", "California", "United States", "US"),
    "new york": ("New York", "New York", "United States", "US"),
    "nyc": ("New York", "New York", "United States", "US"),
    "seattle": ("Seattle", "Washington", "United States", "US"),
    "austin": ("Austin", "Texas", "United States", "US"),
    "boston": ("Boston", "Massachusetts", "United States", "US"),
}

CURRENCY_SYMBOLS: dict[str, str] = {
    "$": "USD",
    "us$": "USD",
    "€": "EUR",
    "£": "GBP",
    "c$": "CAD",
    "ca$": "CAD",
    "a$": "AUD",
    "₹": "INR",
    "₦": "NGN",
    "¥": "JPY",
}
ISO_CURRENCIES = frozenset(
    {"USD", "EUR", "GBP", "CAD", "AUD", "CHF", "SEK", "NOK", "DKK", "PLN", "INR", "SGD", "JPY", "BRL", "MXN", "NGN", "ZAR", "AED", "ILS"}
)


@dataclass
class ParsedLocation:
    location_raw: str | None
    city: str | None = None
    region: str | None = None
    country: str | None = None
    country_code: str | None = None


@dataclass
class ParsedSalary:
    salary_raw: str | None = None
    salary_min: Decimal | None = None
    salary_max: Decimal | None = None
    salary_currency: str | None = None
    salary_period: str | None = None


@dataclass
class NormalizedJobInput:
    external_job_id: str
    title: str
    normalized_title: str
    company_name: str
    normalized_company_name: str
    department: str | None
    description: str
    description_text: str
    location_raw: str | None
    city: str | None
    region: str | None
    country: str | None
    country_code: str | None
    salary_raw: str | None
    salary_min: Decimal | None
    salary_max: Decimal | None
    salary_currency: str | None
    salary_period: str | None
    employment_type: str
    employment_type_raw: str | None
    workplace_type: str
    workplace_type_raw: str | None
    source_job_url: str
    application_url: str
    original_posted_at: datetime | None
    content_hash: str


def clean_whitespace(value: str | None) -> str:
    if not value:
        return ""
    unescaped = html.unescape(value)
    return re.sub(r"\s+", " ", unescaped).strip()


def normalize_title(title: str) -> tuple[str, str]:
    """Return (clean_display_title, normalized_matching_title)."""
    display = clean_whitespace(title)
    lowered = display.lower()
    # Replace common gender markers like (m/f/d), (w/m/d), (f/m/x) for matching
    lowered = re.sub(r"\(\s*[mwfdx]/[mwfdx](?:/[mwfdx])?\s*\)", "", lowered)
    lowered = re.sub(r"[^a-z0-9+#.\s/-]", " ", lowered)
    normalized = re.sub(r"\s+", " ", lowered).strip(" -/")
    return display, normalized


def normalize_company_name(company_name: str) -> tuple[str, str]:
    """Return (clean_display_company, normalized_company_key)."""
    display = clean_whitespace(company_name)
    stripped = LEGAL_ENTITY_SUFFIX_RE.sub(" ", display.lower())
    stripped = re.sub(r"[^a-z0-9\s]", " ", stripped)
    normalized = re.sub(r"\s+", " ", stripped).strip()
    if not normalized:
        normalized = re.sub(r"[^a-z0-9]+", "", display.lower()) or "unknown"
    return display, normalized


def sanitize_description_html(raw_desc: str | None) -> tuple[str, str]:
    """Return (sanitized_html, plain_text_description)."""
    if not raw_desc:
        return "", ""
    decoded = html.unescape(raw_desc) if "&lt;" in raw_desc and "<p" not in raw_desc.lower() else raw_desc
    soup = BeautifulSoup(decoded, "html.parser")
    for tag in soup(["script", "style", "noscript", "iframe", "object", "embed"]):
        tag.decompose()

    raw_html = str(soup)
    clean_html = bleach.clean(
        raw_html,
        tags=ALLOWED_HTML_TAGS,
        attributes=ALLOWED_HTML_ATTRS,
        strip=True,
    ).strip()

    text_soup = BeautifulSoup(clean_html, "html.parser")
    plain_lines: list[str] = []
    for line in text_soup.get_text(separator="\n").splitlines():
        compact = re.sub(r"[ \t]+", " ", line).strip()
        if compact:
            plain_lines.append(compact)
    plain_text = "\n".join(plain_lines)
    return clean_html, plain_text


def html_to_plain_text(raw_desc: str | None) -> str:
    _, plain = sanitize_description_html(raw_desc)
    return plain


def normalize_employment_type(raw_value: str | None) -> str:
    if not raw_value:
        return EmploymentType.UNKNOWN.value
    v = raw_value.lower().replace("_", " ").replace("-", " ").strip()
    if "intern" in v or "working student" in v or "werkstudent" in v or "co op" in v:
        return EmploymentType.INTERNSHIP.value
    if "apprentice" in v or "ausbildung" in v:
        return EmploymentType.APPRENTICESHIP.value
    if "part time" in v or "parttime" in v:
        return EmploymentType.PART_TIME.value
    if "contract" in v or "freelance" in v or "consultant" in v or "1099" in v or "c2c" in v:
        return EmploymentType.CONTRACT.value
    if "temp" in v or "seasonal" in v or "fixed term" in v:
        return EmploymentType.TEMPORARY.value
    if "full time" in v or "fulltime" in v or "permanent" in v or "regular" in v or "festanstellung" in v:
        return EmploymentType.FULL_TIME.value
    return EmploymentType.UNKNOWN.value


def normalize_workplace_type(
    raw_value: str | None,
    *,
    location_raw: str | None = None,
    title: str | None = None,
) -> str:
    candidates = [c for c in (raw_value, location_raw, title) if c]
    for idx, text in enumerate(candidates):
        v = text.lower().replace("_", " ").replace("-", " ")
        if "hybrid" in v:
            return WorkplaceType.HYBRID.value
        if any(tok in v for tok in ("remote", "work from home", "telecommute", "anywhere", "distributed")):
            if "not remote" not in v and "non remote" not in v and "in person" not in v:
                return WorkplaceType.REMOTE.value
        if idx == 0 and any(tok in v for tok in ("on site", "onsite", "in office", "in person", "office", "op locatie")):
            return WorkplaceType.ON_SITE.value
    if title and "in person" in title.lower():
        return WorkplaceType.ON_SITE.value
    return WorkplaceType.UNKNOWN.value


def parse_location(location_raw: str | None) -> ParsedLocation:
    if not location_raw or not clean_whitespace(location_raw):
        return ParsedLocation(location_raw=None)

    raw_clean = clean_whitespace(location_raw)
    # Strip leading workplace wrappers like "Hybrid (New York, NY)" or "Remote - United States"
    unwrapped = re.sub(r"^(?:remote|hybrid|on-?site|in-?office)\s*[-–:|/]\s*", "", raw_clean, flags=re.IGNORECASE)
    m_paren = re.match(r"^(?:remote|hybrid|on-?site)\s*\(([^)]+)\)$", unwrapped, flags=re.IGNORECASE)
    if m_paren:
        unwrapped = m_paren.group(1).strip()

    if unwrapped.lower() in ("remote", "anywhere", "global", "worldwide", "hybrid", "distributed"):
        return ParsedLocation(location_raw=raw_clean)

    # If multiple locations separated by ';' or '•' or '|', parse primary first segment
    primary = re.split(r"[;•|]", unwrapped)[0].strip()
    parts = [p.strip() for p in primary.split(",") if p.strip()]

    # Direct country-only match (e.g. "United States", "Germany", "Remote USA")
    low_primary = re.sub(r"^remote\s+", "", primary.lower()).strip()
    if low_primary in COUNTRY_ALIASES:
        cname, ccode = COUNTRY_ALIASES[low_primary]
        return ParsedLocation(location_raw=raw_clean, country=cname, country_code=ccode)

    if low_primary in KNOWN_CITY_COUNTRIES:
        city, region, cname, ccode = KNOWN_CITY_COUNTRIES[low_primary]
        return ParsedLocation(location_raw=raw_clean, city=city, region=region, country=cname, country_code=ccode)

    city: str | None = None
    region: str | None = None
    country: str | None = None
    country_code: str | None = None

    if len(parts) >= 3:
        last_low = parts[-1].lower().rstrip(".")
        if last_low in COUNTRY_ALIASES:
            country, country_code = COUNTRY_ALIASES[last_low]
            mid = parts[-2].strip()
            if country_code == "US" and mid.upper() in US_STATES:
                region = US_STATES[mid.upper()]
            else:
                region = mid
            city = parts[0]
            return ParsedLocation(location_raw=raw_clean, city=city, region=region, country=country, country_code=country_code)

    if len(parts) == 2:
        first, second = parts[0], parts[1]
        sec_upper = re.sub(r"\s+\d{5}(?:-\d{4})?$", "", second).strip().upper()
        sec_low = second.lower().rstrip(".")
        if sec_upper in US_STATES:
            return ParsedLocation(
                location_raw=raw_clean,
                city=first,
                region=US_STATES[sec_upper],
                country="United States",
                country_code="US",
            )
        if sec_low in US_STATE_NAMES_LOWER:
            _, state_name = US_STATE_NAMES_LOWER[sec_low]
            return ParsedLocation(
                location_raw=raw_clean,
                city=first,
                region=state_name,
                country="United States",
                country_code="US",
            )
        if sec_upper in CA_PROVINCES:
            return ParsedLocation(
                location_raw=raw_clean,
                city=first,
                region=CA_PROVINCES[sec_upper],
                country="Canada",
                country_code="CA",
            )
        if sec_low in COUNTRY_ALIASES:
            cname, ccode = COUNTRY_ALIASES[sec_low]
            return ParsedLocation(
                location_raw=raw_clean,
                city=first,
                country=cname,
                country_code=ccode,
            )

    if len(parts) == 1 and parts[0].lower() in US_STATE_NAMES_LOWER:
        _, state_name = US_STATE_NAMES_LOWER[parts[0].lower()]
        return ParsedLocation(
            location_raw=raw_clean,
            region=state_name,
            country="United States",
            country_code="US",
        )

    return ParsedLocation(location_raw=raw_clean, city=parts[0] if parts else None)


def _to_decimal(val: Any) -> Decimal | None:
    if val is None or val == "":
        return None
    try:
        d = Decimal(str(val).replace(",", "").strip())
        if d <= 0:
            return None
        return d.quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def _detect_period(text: str | None) -> str | None:
    if not text:
        return None
    low = text.lower()
    if any(w in low for w in ("hour", "/hr", "per hr", "hourly")):
        return SalaryPeriod.HOUR.value
    if any(w in low for w in ("month", "/mo", "monthly")):
        return SalaryPeriod.MONTH.value
    if any(w in low for w in ("week", "/wk", "weekly")):
        return SalaryPeriod.WEEK.value
    if any(w in low for w in ("day", "/day", "daily", "per diem")):
        return SalaryPeriod.DAY.value
    if any(w in low for w in ("year", "annual", "/yr", "p.a.", "pa")):
        return SalaryPeriod.YEAR.value
    return None


def parse_salary(
    salary_raw: str | None = None,
    *,
    min_value: Any = None,
    max_value: Any = None,
    currency: str | None = None,
    period: str | None = None,
) -> ParsedSalary:
    """Normalize structured or free-text compensation without inventing missing numbers."""
    dec_min = _to_decimal(min_value)
    dec_max = _to_decimal(max_value)
    norm_currency = currency.upper().strip() if currency and currency.upper().strip() in ISO_CURRENCIES else None
    norm_period = _detect_period(period) or (period.upper() if period in SalaryPeriod.__members__ else None)
    clean_raw = clean_whitespace(salary_raw) if salary_raw else None

    if dec_min is not None or dec_max is not None:
        if dec_min and dec_max and dec_min > dec_max:
            dec_min, dec_max = dec_max, dec_min
        if not norm_period and (dec_min or dec_max):
            ref = dec_max or dec_min
            if ref is not None:
                norm_period = SalaryPeriod.HOUR.value if ref < Decimal("250") else SalaryPeriod.YEAR.value
        if not clean_raw:
            cur = norm_currency or ""
            if dec_min and dec_max:
                clean_raw = f"{cur} {dec_min:,.0f} - {dec_max:,.0f}".strip()
            elif dec_min:
                clean_raw = f"{cur} {dec_min:,.0f}".strip()
            elif dec_max:
                clean_raw = f"{cur} {dec_max:,.0f}".strip()
        return ParsedSalary(
            salary_raw=clean_raw,
            salary_min=dec_min,
            salary_max=dec_max,
            salary_currency=norm_currency,
            salary_period=norm_period,
        )

    if not clean_raw:
        return ParsedSalary()

    # Detect currency from text
    if not norm_currency:
        for iso in ISO_CURRENCIES:
            if re.search(rf"\b{iso}\b", clean_raw, flags=re.IGNORECASE):
                norm_currency = iso
                break
    if not norm_currency:
        for sym, iso in sorted(CURRENCY_SYMBOLS.items(), key=lambda x: -len(x[0])):
            if sym in clean_raw.lower() or sym in clean_raw:
                norm_currency = iso
                break

    if not norm_period:
        norm_period = _detect_period(clean_raw)

    # Extract numeric amounts with optional 'k' suffix
    amount_matches = re.findall(
        r"(?:US\$|CA\$|A\$|[\$€£₹₦¥])?\s*(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*([kK])?\b",
        clean_raw,
    )
    # Only extract if currency or salary context is unambiguous
    if not norm_currency and not norm_period:
        return ParsedSalary(salary_raw=clean_raw)

    values: list[Decimal] = []
    for num_str, k_flag in amount_matches:
        d = _to_decimal(num_str)
        if d is None:
            continue
        if k_flag:
            d = (d * Decimal("1000")).quantize(Decimal("0.01"))
        # Ignore years like 2026 or 401k if isolated without k_flag
        if Decimal("1990") <= d <= Decimal("2035") and not k_flag and norm_period != SalaryPeriod.MONTH.value:
            continue
        if d == Decimal("401000"):
            continue
        values.append(d)

    if not values:
        return ParsedSalary(salary_raw=clean_raw, salary_currency=norm_currency, salary_period=norm_period)

    s_min = values[0]
    s_max = values[1] if len(values) >= 2 else values[0]
    if s_min > s_max:
        s_min, s_max = s_max, s_min
    if not norm_period:
        norm_period = SalaryPeriod.HOUR.value if s_max < Decimal("250") else SalaryPeriod.YEAR.value

    return ParsedSalary(
        salary_raw=clean_raw,
        salary_min=s_min,
        salary_max=s_max,
        salary_currency=norm_currency,
        salary_period=norm_period,
    )


def parse_posting_date(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        ts = float(value)
        if ts > 1e12:
            ts = ts / 1000.0
        if ts <= 0:
            return None
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        if s.isdigit():
            return parse_posting_date(int(s))
        try:
            dt = date_parser.parse(s)
            return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError, OverflowError):
            return None
    return None


def compute_content_hash(
    *,
    normalized_title: str,
    description_text: str,
    location_raw: str | None,
    salary_min: Decimal | None,
    salary_max: Decimal | None,
    salary_currency: str | None,
    employment_type: str,
    workplace_type: str,
    application_url: str | None,
) -> str:
    material = "|".join(
        [
            normalized_title or "",
            (description_text or "")[:10000],
            (location_raw or "").lower().strip(),
            str(salary_min or ""),
            str(salary_max or ""),
            str(salary_currency or ""),
            employment_type or "",
            workplace_type or "",
            canonicalize_url(application_url) or "",
        ]
    )
    return sha256_hex(material)


def normalize_job_record(
    *,
    external_job_id: str,
    title: str,
    company_name: str,
    description_html_or_text: str | None,
    source_job_url: str,
    application_url: str | None = None,
    department: str | None = None,
    location_raw: str | None = None,
    city: str | None = None,
    region: str | None = None,
    country: str | None = None,
    country_code: str | None = None,
    salary_raw: str | None = None,
    salary_min: Any = None,
    salary_max: Any = None,
    salary_currency: str | None = None,
    salary_period: str | None = None,
    employment_type_raw: str | None = None,
    workplace_type_raw: str | None = None,
    original_posted_at: Any = None,
) -> NormalizedJobInput:
    disp_title, norm_title = normalize_title(title)
    disp_company, norm_company = normalize_company_name(company_name)
    desc_html, desc_text = sanitize_description_html(description_html_or_text)

    parsed_loc = parse_location(location_raw)
    final_city = clean_whitespace(city) or parsed_loc.city
    final_region = clean_whitespace(region) or parsed_loc.region
    final_country = clean_whitespace(country) or parsed_loc.country
    final_cc = (country_code or parsed_loc.country_code or "").upper() or None
    if final_country and not final_cc and final_country.lower() in COUNTRY_ALIASES:
        final_country, final_cc = COUNTRY_ALIASES[final_country.lower()]

    final_loc_raw = parsed_loc.location_raw
    if not final_loc_raw and any((final_city, final_region, final_country)):
        final_loc_raw = ", ".join([p for p in (final_city, final_region, final_country) if p])

    parsed_sal = parse_salary(
        salary_raw,
        min_value=salary_min,
        max_value=salary_max,
        currency=salary_currency,
        period=salary_period,
    )

    emp_type = normalize_employment_type(employment_type_raw)
    wp_type = normalize_workplace_type(
        workplace_type_raw,
        location_raw=final_loc_raw,
        title=disp_title,
    )
    posted_dt = parse_posting_date(original_posted_at)

    src_url = source_job_url.strip()
    app_url = (application_url or src_url).strip()

    c_hash = compute_content_hash(
        normalized_title=norm_title,
        description_text=desc_text,
        location_raw=final_loc_raw,
        salary_min=parsed_sal.salary_min,
        salary_max=parsed_sal.salary_max,
        salary_currency=parsed_sal.salary_currency,
        employment_type=emp_type,
        workplace_type=wp_type,
        application_url=app_url,
    )

    return NormalizedJobInput(
        external_job_id=str(external_job_id).strip(),
        title=disp_title,
        normalized_title=norm_title,
        company_name=disp_company,
        normalized_company_name=norm_company,
        department=clean_whitespace(department) or None,
        description=desc_html,
        description_text=desc_text,
        location_raw=final_loc_raw,
        city=final_city or None,
        region=final_region or None,
        country=final_country or None,
        country_code=final_cc,
        salary_raw=parsed_sal.salary_raw,
        salary_min=parsed_sal.salary_min,
        salary_max=parsed_sal.salary_max,
        salary_currency=parsed_sal.salary_currency,
        salary_period=parsed_sal.salary_period,
        employment_type=emp_type,
        employment_type_raw=clean_whitespace(employment_type_raw) or None,
        workplace_type=wp_type,
        workplace_type_raw=clean_whitespace(workplace_type_raw) or None,
        source_job_url=src_url,
        application_url=app_url,
        original_posted_at=posted_dt,
        content_hash=c_hash,
    )
