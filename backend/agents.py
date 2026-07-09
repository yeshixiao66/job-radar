from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from config import get_settings, load_sources


ROLE_KEYWORDS = [
    "工程师",
    "开发",
    "算法",
    "产品",
    "运营",
    "测试",
    "数据",
    "研究员",
    "实习生",
    "管培生",
    "管培",
    "设计师",
    "解决方案",
    "架构师",
    "销售",
    "市场",
    "商务",
    "客户经理",
    "顾问",
    "财务",
    "会计",
    "审计",
    "人力",
    "HR",
    "法务",
    "供应链",
    "采购",
    "质量",
    "安全",
    "运维",
    "硬件",
    "嵌入式",
    "芯片",
    "电气",
    "机械",
    "材料",
    "工艺",
    "职能",
]

STRONG_ROLE_KEYWORDS = [
    "工程师",
    "实习生",
    "管培生",
    "研究员",
    "设计师",
    "解决方案",
    "架构师",
    "客户经理",
    "顾问",
    "会计",
    "审计",
    "法务",
    "采购",
    "运维",
    "开发",
    "算法",
    "专员",
    "经理",
    "分析师",
    "产品运营",
    "内容运营",
    "新媒体运营",
    "数据分析",
    "软件开发",
]

WEAK_ROLE_KEYWORDS = [
    "产品",
    "运营",
    "测试",
    "数据",
    "销售",
    "市场",
    "商务",
    "财务",
    "人力",
    "HR",
    "供应链",
    "质量",
    "安全",
    "硬件",
    "嵌入式",
    "芯片",
    "电气",
    "机械",
    "材料",
    "工艺",
    "职能",
]

ROLE_CONTEXT_KEYWORDS = ["岗", "岗位", "职位", "工程师", "专员", "经理", "实习", "管培", "方向", "分析师"]

JOB_LINK_KEYWORDS = [
    "职位",
    "岗位",
    "招聘",
    "招聘信息",
    "就业信息",
    "宣讲",
    "宣讲会",
    "双选",
    "双选会",
    "job",
    "jobs",
    "position",
    "career",
    "campus",
    "校招",
    "校园招聘",
    "实习",
    "招聘动态",
]

GENERIC_ENTRY_KEYWORDS = [
    "首页",
    "主页",
    "校园招聘",
    "校招",
    "招聘官网",
    "招聘平台",
    "加入我们",
    "人才招聘",
]

SOURCE_AS_COMPANY_KEYWORDS = ["就业信息网", "就业指导", "招聘平台", "校园招聘"]

CITY_NAMES = [
    "北京",
    "上海",
    "广州",
    "深圳",
    "成都",
    "杭州",
    "南京",
    "武汉",
    "西安",
    "重庆",
    "天津",
    "苏州",
    "无锡",
    "宁波",
    "厦门",
    "福州",
    "合肥",
    "长沙",
    "郑州",
    "济南",
    "青岛",
    "大连",
    "沈阳",
    "长春",
    "哈尔滨",
    "石家庄",
    "太原",
    "南昌",
    "南宁",
    "昆明",
    "贵阳",
    "兰州",
    "西宁",
    "银川",
    "乌鲁木齐",
    "海口",
    "珠海",
    "东莞",
    "佛山",
    "中山",
    "惠州",
]

INDUSTRY_OPTIONS = [
    "互联网",
    "人工智能",
    "软件服务",
    "芯片半导体",
    "通信电子",
    "金融",
    "咨询服务",
    "传媒内容",
    "教育培训",
    "医疗健康",
    "生物医药",
    "新能源",
    "汽车制造",
    "先进制造",
    "房地产建筑",
    "消费零售",
    "物流供应链",
    "政务公共",
    "科研院所",
    "其他",
]

ORG_SUFFIX_PATTERN = (
    r"(?:有限公司|有限责任公司|股份有限公司|集团|银行|证券|基金|保险|研究院|研究所|"
    r"科技|智能|咨询|事务所|中心|医院|学校|大学|学院|实验室|委员会|办公室)"
)

KNOWN_COMPANY_ALIASES = [
    "腾讯",
    "华为",
    "百度",
    "阿里",
    "阿里巴巴",
    "字节跳动",
    "美团",
    "京东",
    "网易",
    "科大讯飞",
    "小米",
    "蚂蚁",
    "快手",
    "拼多多",
    "成都农商银行",
    "中金",
    "中建",
    "中信",
    "国家电网",
]

NOISE_LINK_KEYWORDS = [
    "登录",
    "注册",
    "隐私",
    "协议",
    "帮助",
    "关于",
    "联系我们",
    "privacy",
    "login",
    "register",
    "about",
]

_LLM_DISABLED_BY_SETTINGS: dict[str, str] = {}


@dataclass
class AgentResult:
    ok: bool
    data: Any
    latency_ms: int
    message: str


def timed_call(fn):
    start = time.perf_counter()
    try:
        data = fn()
        message = "ok"
        if isinstance(data, tuple) and len(data) == 2:
            data, message = data
        return AgentResult(True, data, int((time.perf_counter() - start) * 1000), str(message))
    except Exception as exc:
        return AgentResult(False, None, int((time.perf_counter() - start) * 1000), str(exc))


def parse_json_payload(content: str, expected: str):
    cleaned = content.strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.I).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    if expected == "array":
        match = re.search(r"\[.*\]", cleaned, re.S)
    else:
        match = re.search(r"\{.*\}", cleaned, re.S)
    target = match.group(0) if match else cleaned
    return json.loads(target)


def normalize_space(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_url(value: Any, base_url: str = "") -> str:
    url = normalize_space(value)
    if not url or url in {"#", "javascript:void(0)", "javascript:;"}:
        return ""
    if url.lower().startswith(("mailto:", "tel:", "javascript:")):
        return ""
    if url.startswith("//"):
        return "https:" + url
    if base_url:
        url = urljoin(base_url, url)
    if not urlparse(url).scheme and "." in url:
        url = "https://" + url
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return ""
    if parsed.netloc.lower() == "oa.hnskxy.com:48084" and parsed.path.rstrip("/") == "/kxy_bybm":
        return f"{parsed.scheme}://{parsed.netloc}/"
    return url.split("#", 1)[0]


def split_locations(value: Any) -> list[str]:
    text = normalize_space(value)
    if not text or text in {"不限", "全国", "多地", "全国多地"}:
        return []
    if "远程" in text:
        return ["远程"]
    if "海外" in text:
        return ["海外"]
    found: list[str] = []
    for city in CITY_NAMES:
        if city in text and city not in found:
            found.append(city)
    if found:
        return found[:8]
    return []


def primary_location(value: Any) -> str:
    locations = split_locations(value)
    if not locations:
        text = normalize_space(value)
        return text if text in {"远程", "海外"} else "不限"
    return locations[0] if len(locations) == 1 else "多地"


def normalized_location_value(value: Any) -> str:
    locations = split_locations(value)
    if locations:
        return "/".join(locations)
    return "不限"


def normalize_industry(value: Any, text: str = "") -> str:
    industry = normalize_space(value)
    if industry in INDUSTRY_OPTIONS and industry != "其他":
        return industry
    corpus = f"{industry} {text}"
    keyword_groups = [
        ("人工智能", ["人工智能", "算法", "大模型", "机器学习", "深度学习", "计算机视觉", "NLP", "AIGC", "智能驾驶"]),
        ("芯片半导体", ["芯片", "半导体", "集成电路", "IC", "EDA", "晶圆", "封装", "嵌入式"]),
        ("通信电子", ["通信", "电子", "电信", "移动", "联通", "运营商", "光电", "射频", "硬件"]),
        ("软件服务", ["软件", "开发", "后端", "前端", "测试", "数据", "云计算", "SaaS", "信息科技", "数字化"]),
        ("互联网", ["互联网", "电商", "平台", "游戏", "社交", "直播", "社区", "产品经理", "用户运营", "腾讯", "阿里", "字节", "美团", "京东", "网易", "快手", "拼多多", "小红书"]),
        ("金融", ["银行", "证券", "基金", "保险", "投行", "资管", "金融", "量化", "风控", "审计"]),
        ("咨询服务", ["咨询", "顾问", "会计师事务所", "事务所", "猎头", "人力资源", "法务", "商务"]),
        ("传媒内容", ["传媒", "媒体", "内容", "新媒体", "编辑", "短视频", "影视", "广告", "品牌", "摄影", "视频", "出镜", "运营实习"]),
        ("教育培训", ["教育", "培训", "学校", "课程", "教研", "老师", "教师", "留学"]),
        ("医疗健康", ["医疗", "医院", "健康", "临床", "器械", "医学"]),
        ("生物医药", ["生物", "医药", "药业", "制药", "药物", "疫苗", "基因"]),
        ("新能源", ["新能源", "电池", "储能", "光伏", "风电", "电力", "能源", "电网"]),
        ("汽车制造", ["汽车", "车载", "整车", "自动驾驶", "座舱", "零部件"]),
        ("先进制造", ["制造", "机械", "材料", "工艺", "自动化", "质量", "供应链", "采购"]),
        ("房地产建筑", ["地产", "房地产", "建筑", "土木", "工程管理", "设计院"]),
        ("消费零售", ["消费", "零售", "快消", "食品", "餐饮", "服装", "美妆"]),
        ("物流供应链", ["物流", "仓储", "供应链", "货运", "航运"]),
        ("政务公共", ["政府", "事业单位", "公共", "高校", "大学", "学院"]),
        ("科研院所", ["研究院", "研究所", "实验室", "科研"]),
    ]
    for target, keywords in keyword_groups:
        if any(keyword in corpus for keyword in keywords):
            return target
    return "其他"


def has_role_signal(text: str) -> bool:
    if any(keyword in text for keyword in STRONG_ROLE_KEYWORDS):
        return True
    return any(keyword in text for keyword in WEAK_ROLE_KEYWORDS) and any(
        keyword in text for keyword in ROLE_CONTEXT_KEYWORDS
    )


def looks_like_generic_entry(title: str) -> bool:
    cleaned = normalize_space(title)
    if not cleaned:
        return True
    if has_role_signal(cleaned):
        return False
    return any(keyword in cleaned for keyword in GENERIC_ENTRY_KEYWORDS)


def looks_like_noise_link(text: str) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in NOISE_LINK_KEYWORDS)


def compact_unique_jobs(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for job in jobs:
        title = normalize_space(job.get("job_title"))
        company = normalize_space(job.get("company_name"))
        url = normalize_space(job.get("announcement_url"))
        if not title or not company or not url:
            continue
        key = "|".join([company, title, url])
        if key in seen:
            continue
        seen.add(key)
        result.append(job)
    return result


def normalize_source_company(source: dict[str, Any]) -> str:
    if source.get("type") in {"university", "aggregator", "job_board"}:
        return ""
    name = normalize_space(source.get("name"))
    for suffix in ["校园招聘", "招聘平台", "招聘官网", "校招", "招聘"]:
        name = name.replace(suffix, "")
    return name.strip()


def looks_like_source_name_company(company: str, source: dict[str, Any]) -> bool:
    company = normalize_space(company)
    source_name = normalize_space(source.get("name"))
    if not company:
        return True
    return company == source_name or any(keyword in company for keyword in SOURCE_AS_COMPANY_KEYWORDS)


def infer_company_name(title: str, summary: str, source: dict[str, Any]) -> str:
    text = normalize_space(f"{title} {summary}")
    source_default = normalize_source_company(source)

    patterns = [
        rf"(?:公司名称|单位名称|招聘单位|用人单位|企业名称)[:：]\s*([^，,；;\n]{{2,60}}?{ORG_SUFFIX_PATTERN})",
        rf"[（(【\[]([^（）()\[\]【】]{{2,60}}?{ORG_SUFFIX_PATTERN})[）)】\]]",
        rf"^([^，,；;:：|（）()【】\s]{{2,60}}?{ORG_SUFFIX_PATTERN})",
        rf"([^，,；;:：|（）()【】\s]{{2,60}}?{ORG_SUFFIX_PATTERN})(?:招聘|校招|实习|岗位|职位|202\d)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            company = normalize_space(match.group(1))
            if company and not looks_like_source_name_company(company, source):
                return company

    for alias in sorted(KNOWN_COMPANY_ALIASES, key=len, reverse=True):
        if text.startswith(alias) or re.search(rf"(^|[｜|\s]){re.escape(alias)}(?:20\d{{2}}|招聘|校招|实习|秋招|春招)", text):
            return alias

    return source_default


def clean_job_title(title: str, company: str) -> str:
    title = normalize_space(title)
    company = normalize_space(company)
    if company and company in title:
        title = title.replace(f"（{company}）", "").replace(f"({company})", "")
        title = re.sub(rf"^{re.escape(company)}[：:|｜\s-]+", "", title)
    title = re.sub(r"^\d+[.、]\s*", "", title)
    return normalize_space(title)


def llm_settings_key(settings) -> str:
    return "|".join([settings.base_url, settings.model, settings.api_key[:8]])


def disabled_llm_message(settings) -> str:
    reason = _LLM_DISABLED_BY_SETTINGS.get(llm_settings_key(settings), "")
    return f"LLM 已跳过：{reason}" if reason else ""


def remember_permanent_llm_failure(settings, exc: Exception) -> None:
    message = str(exc)
    lowered = message.lower()
    permanent_markers = [
        "insufficient_user_quota",
        "quota",
        "401",
        "403",
        "unauthorized",
        "forbidden",
        "no module named 'openai'",
    ]
    if any(marker in lowered for marker in permanent_markers):
        _LLM_DISABLED_BY_SETTINGS[llm_settings_key(settings)] = message[:240]


def llm_create_kwargs(settings, max_tokens: int | None = None) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    if "api.deepseek.com" in settings.base_url.lower():
        # DeepSeek V4 defaults to thinking mode. Structured extraction needs final content,
        # so use non-thinking mode unless the user explicitly configures another gateway.
        kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
    return kwargs


def llm_message_text(message: Any) -> str:
    return str(getattr(message, "content", "") or "").strip()


def empty_llm_content_message(choice: Any) -> str:
    finish_reason = getattr(choice, "finish_reason", "")
    message = getattr(choice, "message", None)
    reasoning = str(getattr(message, "reasoning_content", "") or "")
    if reasoning:
        return f"LLM API 返回 reasoning_content 但 content 为空，finish_reason={finish_reason}；请使用非思考模式或提高 max_tokens"
    return f"LLM API 返回空 content，finish_reason={finish_reason or 'unknown'}"


class SourceAgent:
    name = "Source Agent"

    def run(self) -> AgentResult:
        def work():
            sources = load_sources()
            return sources, f"读取 {len(sources)} 个启用来源"

        return timed_call(work)


class CrawlerAgent:
    name = "Crawler Agent"

    def run(self, source: dict[str, Any]) -> AgentResult:
        def work() -> dict[str, Any]:
            session = requests.Session()
            page = self._fetch_page(session, source, source["url"])
            pages = [page]
            max_pages = int(source.get("max_pages") or (6 if source.get("type") in {"university", "aggregator"} else 4))
            for link in self._candidate_links(page["links"], page["url"]):
                if len(pages) >= max_pages:
                    break
                try:
                    child = self._fetch_page(session, source, link["url"], link.get("label", ""))
                    pages.append(child)
                except Exception:
                    continue

            data = dict(page)
            data["pages"] = pages
            text_len = sum(len(item.get("content", "")) for item in pages)
            link_len = sum(len(item.get("links", [])) for item in pages)
            return data, f"抓取 {len(pages)} 页，正文 {text_len} 字，链接 {link_len} 个"

        return timed_call(work)

    def _fetch_page(
        self,
        session: requests.Session,
        source: dict[str, Any],
        url: str,
        parent_label: str = "",
    ) -> dict[str, Any]:
        response = session.get(
            url,
            timeout=get_settings().request_timeout,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0 Safari/537.36 JobRadar/0.2"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.6",
            },
        )
        response.raise_for_status()
        response.encoding = response.apparent_encoding or response.encoding

        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        title = (soup.title.string.strip() if soup.title and soup.title.string else parent_label or source["name"])
        text = "\n".join(line.strip() for line in soup.get_text("\n").splitlines() if line.strip())

        links = []
        seen = set()
        for a in soup.find_all("a", href=True):
            href = urljoin(url, a["href"])
            parsed = urlparse(href)
            if parsed.scheme not in {"http", "https"}:
                continue
            href = href.split("#", 1)[0]
            if href in seen:
                continue
            seen.add(href)
            label = a.get_text(" ", strip=True)
            links.append({"label": label, "url": href})

        return {
            "source": source,
            "title": title[:200],
            "content": text[:12000],
            "links": links[:120],
            "url": url,
            "status_code": response.status_code,
            "parent_label": parent_label,
        }

    def _candidate_links(self, links: list[dict[str, str]], base_url: str) -> list[dict[str, str]]:
        base_host = urlparse(base_url).netloc
        scored: list[tuple[int, dict[str, str]]] = []
        for link in links:
            label = normalize_space(link.get("label"))
            url = normalize_space(link.get("url"))
            if not url or url == base_url:
                continue
            text = f"{label} {url}"
            lowered = text.lower()
            if looks_like_noise_link(text):
                continue
            if urlparse(url).netloc != base_host and not has_role_signal(text):
                continue
            score = 0
            for keyword in JOB_LINK_KEYWORDS:
                if keyword.lower() in lowered:
                    score += 2
            if has_role_signal(text):
                score += 4
            if any(part in lowered for part in ["/job", "/jobs", "position", "recruit", "campus"]):
                score += 2
            if score > 0:
                scored.append((score, link))

        scored.sort(key=lambda item: item[0], reverse=True)
        result: list[dict[str, str]] = []
        seen = set()
        for _, link in scored:
            url = link["url"]
            if url in seen:
                continue
            seen.add(url)
            result.append(link)
            if len(result) >= 6:
                break
        return result


class ExtractorAgent:
    name = "Extractor Agent"

    def run(self, page: dict[str, Any]) -> AgentResult:
        def work() -> list[dict[str, Any]]:
            pages = page.get("pages") if isinstance(page.get("pages"), list) else [page]
            jobs: list[dict[str, Any]] = []
            messages: list[str] = []

            for item in pages[:4]:
                llm_jobs, llm_message = self._extract_with_llm(item)
                if llm_jobs:
                    jobs.extend(self._clean_jobs(llm_jobs, item))
                    messages.append(f"{item.get('title', '')[:30]}: {llm_message}")
                    continue

                rule_jobs = self._extract_with_rules(item)
                jobs.extend(rule_jobs)
                messages.append(f"{item.get('title', '')[:30]}: {llm_message}；规则抽取 {len(rule_jobs)} 条")

            jobs = compact_unique_jobs(jobs)
            if not jobs:
                return [], "未发现可入库的具体岗位；" + " | ".join(messages[:3])
            return jobs, f"抽取 {len(jobs)} 条；" + " | ".join(messages[:3])

        return timed_call(work)

    def _extract_with_llm(self, page: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
        settings = get_settings()
        if not (settings.api_key and settings.base_url and settings.model):
            return [], "未配置 LLM API"
        disabled = disabled_llm_message(settings)
        if disabled:
            return [], disabled

        try:
            from openai import OpenAI

            client = OpenAI(api_key=settings.api_key, base_url=settings.base_url, timeout=settings.llm_timeout)
            prompt = f"""
请从招聘网页中抽取岗位信息，严格返回 JSON 数组，不要输出解释。
字段：
publish_date, company_name, job_title, announcement_url, apply_url,
batch, location, deadline, raw_summary。
找不到的字段用空字符串。不要编造投递链接。

网页标题：{page["title"]}
网页链接：{page["url"]}
正文：
{page["content"][:6000]}
链接：
{json.dumps(page["links"][:30], ensure_ascii=False)}
"""
            response = client.chat.completions.create(
                model=settings.model,
                messages=[
                    {"role": "system", "content": "你是招聘信息抽取 Agent，只返回可解析 JSON。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                **llm_create_kwargs(settings, max_tokens=4096),
            )
            choices = getattr(response, "choices", None) or []
            if not choices or getattr(choices[0], "message", None) is None:
                return [], "LLM API 响应不含 choices/message，可能是模型名、接口兼容或额度异常"
            content = llm_message_text(choices[0].message)
            if not content:
                return [], empty_llm_content_message(choices[0])
            jobs = parse_json_payload(content, "array")
            if not isinstance(jobs, list):
                return [], "LLM API 返回不是 JSON 数组"
            if not jobs:
                return [], "LLM API 调用成功但未抽取到岗位"
            return jobs, "LLM API 调用成功"
        except Exception as exc:
            remember_permanent_llm_failure(settings, exc)
            return [], f"LLM API 抽取失败：{exc}"

    def _clean_jobs(self, jobs: list[dict[str, Any]], page: dict[str, Any]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for job in jobs:
            if not isinstance(job, dict):
                continue
            title = normalize_space(job.get("job_title"))
            if looks_like_generic_entry(title):
                continue
            cleaned = dict(job)
            cleaned["announcement_url"] = normalize_url(cleaned.get("announcement_url"), page.get("url", "")) or page.get("url", "")
            cleaned["apply_url"] = normalize_url(cleaned.get("apply_url"), cleaned["announcement_url"])
            cleaned.setdefault("raw_summary", "")
            company = normalize_space(cleaned.get("company_name"))
            source = page.get("source", {})
            if looks_like_source_name_company(company, source):
                company = infer_company_name(title, cleaned.get("raw_summary", ""), source)
            cleaned["company_name"] = company
            cleaned["job_title"] = clean_job_title(title, company)
            cleaned["location"] = normalized_location_value(cleaned.get("location"))
            result.append(cleaned)
        return result

    def _extract_with_rules(self, page: dict[str, Any]) -> list[dict[str, Any]]:
        source = page["source"]
        content = page["content"]
        page_title = normalize_space(page.get("title"))
        apply_url = ""
        for link in page["links"]:
            text = f'{link.get("label", "")} {link.get("url", "")}'
            if any(key in text for key in ["投递", "申请", "apply", "校招", "join", "career"]):
                apply_url = normalize_url(link["url"], page["url"])
                break

        default_company = normalize_source_company(source)
        date_match = re.search(r"(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})", content)
        publish_date = ""
        if date_match:
            publish_date = f"{date_match.group(1)}-{int(date_match.group(2)):02d}-{int(date_match.group(3)):02d}"

        batch = ""
        for pattern in ["2026届春招", "2026届秋招", "2027届实习", "2028届实习", "日常实习", "暑期实习", "补录"]:
            if pattern in content or pattern in page["title"]:
                batch = pattern
                break

        locations = split_locations(content)

        def make_job(title: str, announcement_url: str, summary: str = "") -> dict[str, Any]:
            company = infer_company_name(title, summary or content[:500], source) or default_company
            clean_title = clean_job_title(title, company)
            return {
                "publish_date": publish_date,
                "company_name": company,
                "job_title": clean_title,
                "announcement_url": normalize_url(announcement_url, page["url"]),
                "apply_url": apply_url if announcement_url == page["url"] else normalize_url(announcement_url, page["url"]),
                "batch": batch,
                "location": "/".join(locations) if locations else "不限",
                "deadline": "",
                "raw_summary": summary or content[:240],
            }

        jobs: list[dict[str, Any]] = []
        for link in page["links"]:
            label = normalize_space(link.get("label"))
            url = normalize_space(link.get("url"))
            text = f"{label} {url}"
            if not label or looks_like_noise_link(text):
                continue
            if has_role_signal(text) and not looks_like_generic_entry(label):
                jobs.append(make_job(label, url, label))

        for line in content.splitlines():
            title = normalize_space(line)
            if len(title) < 4 or len(title) > 80:
                continue
            if has_role_signal(title) and not looks_like_generic_entry(title):
                jobs.append(make_job(title, page["url"], title))
            if len(jobs) >= 20:
                break

        if has_role_signal(page_title) and not looks_like_generic_entry(page_title):
            jobs.append(make_job(page_title, page["url"]))

        return compact_unique_jobs(jobs)


class VerifierAgent:
    name = "Verifier Agent"

    def run(self, job: dict[str, Any], source: dict[str, Any]) -> AgentResult:
        def work() -> dict[str, Any]:
            source_type = source.get("type", "")
            apply_url = job.get("apply_url", "")
            title = job.get("job_title", "")
            summary = job.get("raw_summary", "")
            role_keywords = ["工程师", "实习", "管培", "开发", "算法", "产品", "运营", "测试", "数据", "研究员"]
            is_generic_entry = not any(keyword in title for keyword in role_keywords)
            is_official = source_type == "official"
            confidence = "待核验"
            status = "待核验"

            if is_official and (is_generic_entry or looks_like_generic_entry(title)):
                confidence = "低"
                status = "仅入口页，待深挖"
            elif is_official and apply_url:
                confidence = "高"
                status = "可投递"
            elif is_official:
                confidence = "中"
                status = "缺少投递链接"
            elif source_type == "university":
                confidence = "中高" if apply_url else "中"
                status = "可投递" if apply_url else "待补投递链接"
            elif apply_url:
                confidence = "中"
                status = "可投递"

            job.update(
                {
                    "source_name": source.get("name", ""),
                    "source_type": source_type,
                    "confidence": confidence,
                    "status": status,
                }
            )
            return job

        return timed_call(work)


class ClassifierAgent:
    name = "Classifier Agent"

    def run(self, job: dict[str, Any], source: dict[str, Any]) -> AgentResult:
        def work() -> dict[str, Any]:
            classified, llm_message = self._classify_with_llm(job)
            if classified:
                job.update(classified)
                message = llm_message
            else:
                job.update(self._classify_with_rules(job, source))
                message = f"{llm_message}；规则兜底分类完成"

            key = "|".join(
                [
                    job.get("company_name", ""),
                    job.get("job_title", ""),
                    job.get("announcement_url", ""),
                ]
            )
            job["id"] = hashlib.sha1(key.encode("utf-8")).hexdigest()
            return job, message

        return timed_call(work)

    def _classify_with_llm(self, job: dict[str, Any]) -> tuple[dict[str, Any], str]:
        settings = get_settings()
        if not (settings.api_key and settings.base_url and settings.model):
            return {}, "未配置 LLM API"
        disabled = disabled_llm_message(settings)
        if disabled:
            return {}, disabled

        try:
            from openai import OpenAI

            client = OpenAI(api_key=settings.api_key, base_url=settings.base_url, timeout=settings.llm_timeout)
            prompt = f"""
请对招聘岗位分类，严格返回 JSON 对象。
字段：industry, company_type, batch, location, hot_score。
industry 从 互联网、人工智能、软件服务、芯片半导体、通信电子、金融、咨询服务、传媒内容、教育培训、医疗健康、生物医药、新能源、汽车制造、先进制造、房地产建筑、消费零售、物流供应链、政务公共、科研院所、其他 中选择。
company_type 从 民营、国企、央企、外企、事业单位、研究院、其他 中选择。
batch 如 2026届春招、2026届秋招、2027届实习、日常实习、补录。
location 只返回一个主要城市；如果明确有多个城市，返回“多地”；不要把一串城市全部放进 location。
hot_score 为 1 到 5 的整数。
岗位信息：{json.dumps(job, ensure_ascii=False)}
"""
            response = client.chat.completions.create(
                model=settings.model,
                messages=[
                    {"role": "system", "content": "你是招聘岗位分类 Agent，只返回 JSON。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                **llm_create_kwargs(settings, max_tokens=1024),
            )
            choices = getattr(response, "choices", None) or []
            if not choices or getattr(choices[0], "message", None) is None:
                return {}, "LLM API 响应不含 choices/message，可能是模型名、接口兼容或额度异常"
            content = llm_message_text(choices[0].message)
            if not content:
                return {}, empty_llm_content_message(choices[0])
            data = parse_json_payload(content, "object")
            if not isinstance(data, dict):
                return {}, "LLM API 返回不是 JSON 对象"
            if not data:
                return {}, "LLM API 调用成功但分类为空"
            text = " ".join(str(job.get(k, "")) for k in ["company_name", "job_title", "raw_summary"])
            data["industry"] = normalize_industry(data.get("industry"), text)
            data["location"] = normalized_location_value(data.get("location") or job.get("location"))
            return data, "LLM API 分类完成"
        except Exception as exc:
            remember_permanent_llm_failure(settings, exc)
            return {}, f"LLM API 分类失败：{exc}"

    def _classify_with_rules(self, job: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
        text = " ".join(str(job.get(k, "")) for k in ["company_name", "job_title", "raw_summary"])
        industry = normalize_industry(source.get("industry_hint"), text)

        company_type = source.get("company_type_hint") or "其他"
        if any(k in text for k in ["国家电网", "中石油", "中石化", "中国移动", "中国电信", "中国联通"]):
            company_type = "央企"

        batch = job.get("batch") or ("2027届实习" if "实习" in text else "待分类")
        hot_score = 3
        if source.get("type") == "official":
            hot_score += 1
        if job.get("apply_url"):
            hot_score += 1

        return {
            "industry": industry,
            "company_type": company_type,
            "batch": batch,
            "location": normalized_location_value(job.get("location")),
            "hot_score": min(hot_score, 5),
        }
