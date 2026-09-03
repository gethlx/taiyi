#!/usr/bin/env python3
"""Import the project's selected public-domain electronic texts.

The importer saves an immutable-ish HTML/API snapshot under ``refs/snap`` and
builds one complete Markdown file per work under ``kb/texts``.  It deliberately
does not touch ``kb/manifest.json``: the navigation ledger is updated only after
the generated texts have been reviewed.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from lxml import html


WORKSPACE = Path(__file__).resolve().parents[1]
WIKISOURCE_API = "https://zh.wikisource.org/w/api.php"
USER_AGENT = "Zhongyi-classics-corpus/1.0 (public-text snapshot)"
CONVERSION = "public-text-import-v1"


WIKI_WORKS = (
    {
        "work_id": "T01-CT-WS",
        "layer_id": "01",
        "work": "周易参同契",
        "filename": "01B_参同契.md",
        "snapshot": "refs/snap/wiki/T01-CT-WS.json",
        "pages": ["周易參同契/全覽"],
        "source_edition": "维基文库《周易参同契》35章社区电子文本",
        "expected_scope": "大易总叙章第一至自叙启后章第三十五",
        "verification_status": "社区电子文本；未与专门校勘本逐字核校",
        "calling_role": "01元典层的易理气化展开；不替代《周易》",
        "normalization_note": "来源正文1个私用区字符转为□，保留缺字状态",
    },
    {
        "work_id": "T02-TS-WS",
        "layer_id": "02",
        "work": "黄帝内经太素",
        "filename": "02D_太素.md",
        "snapshot": "refs/snap/wiki/T02-TS-WS.json",
        "pages": ["黃帝內經太素"],
        "source_edition": "维基文库《黄帝内经太素》社区电子文本",
        "expected_scope": "传世卷次；原书残缺处从来源保留",
        "verification_status": "社区电子文本；用于《内经》主题聚合与检索补足",
        "calling_role": "《素问》《灵枢》检索不完整时的主题聚合与经文对读",
    },
    {
        "work_id": "T03-ZB-WS",
        "layer_id": "03/04",
        "work": "诸病源候论",
        "filename": "03C_诸病源候论.md",
        "snapshot": "refs/snap/wiki/T03-ZB-WS.json",
        "pages": ["諸病源候論"],
        "source_edition": "维基文库《诸病源候论》50卷社区电子文本",
        "expected_scope": "序及50卷病候",
        "verification_status": "社区电子文本；未与专门校勘本逐字核校",
        "calling_role": "仲景模型未能解释全部症候时补充病源、病位、候群与演变",
    },
)


HUANGTING = {
    "work_id": "T02-HT-CT",
    "layer_id": "02",
    "work": "黄庭内景五脏六腑补泻图",
    "filename": "02E_黄庭补泻图.md",
    "snapshot": "refs/snap/ctext/T02-HT-CT.json",
    "url": "https://ctext.org/wiki.pl?chapter=190571&if=gb",
    "scan_file": "99058",
    "source_edition": "中国哲学书电子化计划维基电子文本及对应影像页索引",
    "expected_scope": "并序、五脏图与胆腑图位、脏腑说明、修养、病候、方药、六气与导引",
    "verification_status": "社区电子文本；正文页未嵌入五幅脏图和一幅胆腑图，图位链接至对应来源影像",
    "calling_role": "取得《内经》《难经》医学坐标后，条件性补充五脏内景与形神关系",
}


JIAYI_CTEXT = {
    "work_id": "T09-JY-CT",
    "layer_id": "09",
    "work": "针灸甲乙经",
    "filename": "09_针灸甲乙经.md",
    "snapshot": "refs/snap/ctext/T09-JY-CT.json",
    "index_url": "https://ctext.org/wiki.pl?if=gb&res=7193010",
    "pages": (
        ("序", 218661),
        ("卷一", 359364),
        ("卷二", 122895),
        ("卷三", 169146),
        ("卷四", 445071),
        ("卷五", 334086),
        ("卷六", 411246),
        ("卷七", 429921),
        ("卷八", 281922),
        ("卷九", 337845),
        ("卷十", 486297),
        ("卷十一", 285135),
        ("卷十二", 406191),
    ),
    "source_edition": "中国哲学书电子化计划《针灸甲乙经》字符识别文本及对应底本影像关联",
    "expected_scope": "序及12卷完整保存；运行时以卷1至卷7承担经络形位调用",
    "verification_status": "字符识别文本已关联底本影像；未与专门校勘本逐字核校",
    "calling_role": "卷1至卷7用于经脉循行、表里、病位与脏腑气血关系",
}


def now_iso() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).replace(microsecond=0).isoformat()


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt == 4:
                raise
            retry_after = exc.headers.get("Retry-After")
            delay = min(float(retry_after), 45.0) if retry_after else 2.0 ** (attempt + 1)
            print(f"rate limited; retrying in {delay:g}s")
            time.sleep(delay)
        except urllib.error.URLError:
            if attempt == 4:
                raise
            time.sleep(2.0 ** attempt)
    raise RuntimeError("unreachable")


def strip_markup(value: str) -> str:
    if not value:
        return ""
    return " ".join(html.fromstring(f"<span>{value}</span>").text_content().split())


def source_url(title: str, revision_id: int) -> str:
    query = urllib.parse.urlencode(
        {"title": title, "oldid": revision_id, "variant": "zh-hans"}
    )
    return f"https://zh.wikisource.org/w/index.php?{query}"


def fetch_wikisource_page(requested_title: str) -> dict[str, object]:
    query = urllib.parse.urlencode(
        {
            "action": "parse",
            "page": requested_title,
            "prop": "text|displaytitle|revid",
            "format": "json",
            "formatversion": "2",
            "redirects": "1",
            "variant": "zh-hans",
        }
    )
    api_url = f"{WIKISOURCE_API}?{query}"
    payload = json.loads(fetch(api_url).decode("utf-8"))
    if "error" in payload:
        raise RuntimeError(f"Wikisource error for {requested_title}: {payload['error']}")
    parsed = payload["parse"]
    revision_id = int(parsed["revid"])
    resolved_title = str(parsed.get("title") or requested_title)
    return {
        "requested_title": requested_title,
        "resolved_title": resolved_title,
        "display_title": strip_markup(str(parsed.get("displaytitle") or resolved_title)),
        "revision_id": revision_id,
        "source_url": source_url(resolved_title, revision_id),
        "html": parsed["text"],
    }


def remove_element(element) -> None:
    parent = element.getparent()
    if parent is not None:
        parent.remove(element)


def clean_wikisource_root(raw_html: str):
    root = html.fromstring(raw_html)
    bodies = root.xpath(
        './/*[contains(concat(" ", normalize-space(@class), " "), " mw-parser-output ")]'
    )
    body = copy.deepcopy(bodies[0] if bodies else root)
    noise_xpath = (
        ".//style | .//script | .//link | .//meta | .//table | "
        './/*[contains(concat(" ", normalize-space(@class), " "), " mw-editsection ")] | '
        './/*[contains(concat(" ", normalize-space(@class), " "), " headerContainer ")] | '
        './/*[contains(concat(" ", normalize-space(@class), " "), " noprint ")] | '
        './/*[contains(concat(" ", normalize-space(@class), " "), " ws-noexport ")] | '
        './/*[contains(concat(" ", normalize-space(@class), " "), " sisterproject ")] | '
        './/*[contains(concat(" ", normalize-space(@class), " "), " references ")] | '
        './/*[contains(concat(" ", normalize-space(@class), " "), " reference ")]'
    )
    for element in body.xpath(noise_xpath):
        remove_element(element)
    return body


def block_text(element) -> str:
    element = copy.deepcopy(element)
    for br in element.xpath(".//br"):
        br.tail = "\n" + (br.tail or "")
    text = element.text_content().replace("\xa0", " ").replace("\u3000", " ")
    text = "".join("□" if 0xE000 <= ord(char) <= 0xF8FF else char for char in text)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def wikisource_html_to_markdown(raw_html: str) -> str:
    body = clean_wikisource_root(raw_html)
    blocks: list[str] = []
    for element in body.iter():
        if not isinstance(element.tag, str):
            continue
        tag = element.tag.lower()
        classes = set((element.get("class") or "").split())
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            text = re.sub(r"\s*\[编辑\]\s*$", "", block_text(element))
            if text:
                level = min(int(tag[1]) + 1, 6)
                blocks.append(f"{'#' * level} {text}")
        elif tag == "p":
            text = block_text(element)
            if text:
                blocks.append(text)
        elif tag == "li" and not element.xpath("./p"):
            text = block_text(element)
            if text:
                blocks.append(f"- {text}")
        elif tag == "blockquote":
            text = block_text(element)
            if text:
                blocks.append("\n".join(f"> {line}" for line in text.splitlines()))
        elif tag == "div" and classes.intersection({"poem", "verse"}):
            text = block_text(element)
            if text:
                blocks.append(text)
    markdown = "\n\n".join(blocks)
    markdown = re.sub(r"\n{3,}", "\n\n", markdown).strip()
    return markdown + "\n"


def yaml_quoted(value: object) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def frontmatter(work: dict[str, object], fetched_at: str, page_count: int, site: str) -> str:
    fields = [
        ("document_type", "external-text-snapshot"),
        ("work_id", work["work_id"]),
        ("layer_id", work["layer_id"]),
        ("work", work["work"]),
        ("source_site", site),
        ("source_snapshot", work["snapshot"]),
        ("source_edition", work["source_edition"]),
        ("source_page_count", page_count),
        ("expected_scope", work["expected_scope"]),
        ("fetched_at", fetched_at),
        ("conversion", CONVERSION),
        ("language_variant", "zh-hans"),
        ("verification_status", work["verification_status"]),
        ("calling_role", work["calling_role"]),
    ]
    if work.get("normalization_note"):
        fields.append(("normalization_note", work["normalization_note"]))
    fields.append(
        (
            "license_note",
            "古籍原作属公有领域；电子页面编辑内容按来源站点许可使用，页面链接与修订信息见来源快照",
        )
    )
    lines = ["---"]
    lines.extend(f"{key}: {yaml_quoted(value)}" for key, value in fields)
    lines.append("---")
    return "\n".join(lines) + "\n"


def write_json(path: Path, payload: dict[str, object], force: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not force:
        raise FileExistsError(f"snapshot exists; use --force to replace: {path}")
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def write_markdown(path: Path, text: str, force: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not force:
        raise FileExistsError(f"text exists; use --force to replace: {path}")
    path.write_text(text, encoding="utf-8", newline="\n")


def import_wiki_work(work: dict[str, object], force: bool) -> None:
    fetched_at = now_iso()
    pages = []
    for title in work["pages"]:
        pages.append(fetch_wikisource_page(str(title)))
        time.sleep(0.75)
    snapshot_path = WORKSPACE / str(work["snapshot"])
    write_json(
        snapshot_path,
        {
            "snapshot_version": "wikisource-work-snapshot-v1",
            "work_id": work["work_id"],
            "title": work["work"],
            "fetched_at": fetched_at,
            "api_url": WIKISOURCE_API,
            "language_variant": "zh-hans",
            "pages": pages,
        },
        force,
    )

    slug = str(work["work_id"]).lower()
    sections = [
        frontmatter(work, fetched_at, len(pages), "中文维基文库"),
        f'<a id="{slug}"></a>\n# {work["work"]}\n',
        "> 来源：中文维基文库简体渲染固定快照。正文保留来源残缺与异文，用于经典研究与检索。\n",
    ]
    for index, page in enumerate(pages, 1):
        converted = wikisource_html_to_markdown(str(page["html"]))
        if len(converted) < 30:
            raise RuntimeError(f"converted page is unexpectedly short: {page['resolved_title']}")
        sections.append(
            f'<a id="{slug}-source-{index:03d}"></a>\n'
            f'## {page["display_title"]}\n\n'
            f'<!-- source-title: {page["resolved_title"]}; revision-id: {page["revision_id"]}; '
            f'source-url: {page["source_url"]} -->\n\n'
            f"{converted}"
        )
    target = WORKSPACE / "kb" / "texts" / str(work["filename"])
    write_markdown(target, "\n".join(section.rstrip() for section in sections) + "\n", force)
    print(f"imported {work['work_id']}: {len(pages)} page(s) -> {target.relative_to(WORKSPACE)}")


def ctext_scan_page(first_cell) -> str | None:
    links = first_cell.xpath('.//a[contains(@href, "library.pl")]')
    if not links:
        return None
    query = urllib.parse.parse_qs(urllib.parse.urlparse(links[0].get("href")).query)
    values = query.get("page")
    return values[0] if values else None


def huangting_heading(text: str, row_number: int) -> int | None:
    if row_number == 1:
        return 1
    if row_number == 2:
        return 2
    if re.fullmatch(
        r"[肺心肝脾腎肾]臟圖|[肺心肝脾腎肾]藏圖|[膽胆]腑圖", text
    ):
        return 2
    if len(text) <= 24 and (
        text.endswith("法")
        or "導引法" in text
        or "导引法" in text
        or text in {"六氣法", "六气法", "修養法", "修养法"}
    ):
        return 3
    return None


def import_huangting(force: bool) -> None:
    work = HUANGTING
    fetched_at = now_iso()
    raw = fetch(str(work["url"]))
    decoded = raw.decode("utf-8")
    root = html.fromstring(raw)
    content = root.get_element_by_id("content")
    tables = content.xpath("./table")
    text_tables = [table for table in tables if len(table.xpath(".//tr/td[@class='ctext']")) > 20]
    if len(text_tables) != 1:
        raise RuntimeError("cannot identify the CText electronic-text table")
    table = text_tables[0]

    snapshot_path = WORKSPACE / str(work["snapshot"])
    write_json(
        snapshot_path,
        {
            "snapshot_version": "ctext-work-snapshot-v1",
            "work_id": work["work_id"],
            "title": work["work"],
            "fetched_at": fetched_at,
            "source_url": work["url"],
            "scan_file": work["scan_file"],
            "html": decoded,
        },
        force,
    )

    slug = str(work["work_id"]).lower()
    blocks = [
        frontmatter(work, fetched_at, 1, "中国哲学书电子化计划"),
        f'<a id="{slug}"></a>\n# {work["work"]}\n',
        "> 来源：中国哲学书电子化计划电子文本固定快照。正文页没有嵌入五幅脏图和一幅胆腑图，以下在各图位保留对应影像页链接。\n",
    ]
    for row_number, row in enumerate(table.xpath(".//tr"), 1):
        cells = row.xpath("./td")
        if len(cells) < 2:
            continue
        text = block_text(cells[-1])
        if not text:
            continue
        page = ctext_scan_page(cells[0])
        blocks.append(f"<!-- source-row: {row_number}; scan-page: {page or 'unknown'} -->")
        level = huangting_heading(text, row_number)
        if row_number == 1:
            continue
        if level:
            if row_number == 2:
                text = text.replace("_", "——", 1)
            blocks.append(f"{'#' * level} {text}")
        else:
            blocks.append(text)
        if re.fullmatch(
            r"[肺心肝脾腎肾]臟圖|[肺心肝脾腎肾]藏圖|[膽胆]腑圖", text
        ) and page:
            scan_url = (
                "https://ctext.org/library.pl?"
                + urllib.parse.urlencode(
                    {"if": "gb", "file": work["scan_file"], "page": page}
                )
            )
            blocks.append(f"> 图位：电子正文未嵌图；[查看来源影像第{page}页]({scan_url})。")

    target = WORKSPACE / "kb" / "texts" / str(work["filename"])
    markdown = "\n\n".join(block.rstrip() for block in blocks) + "\n"
    if len(markdown) < 5_000:
        raise RuntimeError("converted Huangting text is unexpectedly short")
    write_markdown(target, markdown, force)
    print(f"imported {work['work_id']}: 1 page -> {target.relative_to(WORKSPACE)}")


def ctext_inline_text(cell) -> str:
    cell = copy.deepcopy(cell)
    for note in cell.xpath(
        './/*[contains(concat(" ", normalize-space(@class), " "), " inlinecomment ")]'
    ):
        note_text = block_text(note)
        note.clear()
        note.text = f"〈{note_text}〉" if note_text else ""
    return block_text(cell)


def import_jiayi_ctext(force: bool) -> None:
    work = JIAYI_CTEXT
    fetched_at = now_iso()
    snapshot_pages: list[dict[str, object]] = []
    markdown_pages: list[tuple[str, int, list[str]]] = []

    for label, chapter_id in work["pages"]:
        url = f"https://ctext.org/wiki.pl?{urllib.parse.urlencode({'chapter': chapter_id, 'if': 'gb'})}"
        raw = fetch(url)
        decoded = raw.decode("utf-8")
        if "\ufffd" in decoded:
            raise RuntimeError(f"replacement character in CText chapter {chapter_id}")
        root = html.fromstring(raw)
        content = root.get_element_by_id("content")
        tables = content.xpath("./table")
        text_tables = [table for table in tables if len(table.xpath(".//tr")) > 5]
        if len(text_tables) != 1:
            raise RuntimeError(f"cannot identify CText table for chapter {chapter_id}")

        blocks: list[str] = []
        for row in text_tables[0].xpath(".//tr"):
            heading = row.xpath("./td[@colspan]/h2")
            if heading:
                title = block_text(heading[0]).strip("《》 ")
                if title:
                    blocks.append(f"### {title}")
                continue
            cells = row.xpath("./td")
            if len(cells) < 2:
                continue
            paragraph = ctext_inline_text(cells[-1])
            if paragraph:
                blocks.append(paragraph)
        if not blocks:
            raise RuntimeError(f"empty CText conversion for chapter {chapter_id}")
        snapshot_pages.append(
            {"label": label, "chapter_id": chapter_id, "source_url": url, "html": decoded}
        )
        markdown_pages.append((label, chapter_id, blocks))
        time.sleep(0.4)

    snapshot_path = WORKSPACE / str(work["snapshot"])
    write_json(
        snapshot_path,
        {
            "snapshot_version": "ctext-work-snapshot-v1",
            "work_id": work["work_id"],
            "title": work["work"],
            "fetched_at": fetched_at,
            "index_url": work["index_url"],
            "pages": snapshot_pages,
        },
        force,
    )

    slug = str(work["work_id"]).lower()
    sections = [
        frontmatter(work, fetched_at, len(markdown_pages), "中国哲学书电子化计划"),
        f'<a id="{slug}"></a>\n# {work["work"]}\n',
        "> 来源：中国哲学书电子化计划字符识别文本固定快照；各行与来源影像关联，正文保留来源异文。\n",
    ]
    for index, (label, chapter_id, blocks) in enumerate(markdown_pages, 1):
        url = snapshot_pages[index - 1]["source_url"]
        sections.append(
            f'<a id="{slug}-source-{index:03d}"></a>\n'
            f"## {label}\n\n"
            f"<!-- ctext-chapter-id: {chapter_id}; source-url: {url} -->\n\n"
            + "\n\n".join(blocks)
        )
    target = WORKSPACE / "kb" / "texts" / str(work["filename"])
    markdown = "\n".join(section.rstrip() for section in sections) + "\n"
    if len(markdown) < 100_000:
        raise RuntimeError("converted Jiayi text is unexpectedly short")
    write_markdown(target, markdown, force)
    print(
        f"imported {work['work_id']}: {len(markdown_pages)} page(s) -> "
        f"{target.relative_to(WORKSPACE)}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--force", action="store_true", help="replace existing snapshots and generated texts"
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    for work in WIKI_WORKS:
        import_wiki_work(work, args.force)
    import_huangting(args.force)
    import_jiayi_ctext(args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
