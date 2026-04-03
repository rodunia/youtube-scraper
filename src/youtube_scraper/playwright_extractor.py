from __future__ import annotations

import re
from dataclasses import dataclass


class PlaywrightExtractorError(RuntimeError):
    """Playwright extraction failed."""


@dataclass
class WebComment:
    comment_id: str
    raw_commenter_id: str
    raw_text: str
    like_count: int
    reply_count: int
    published_at: str
    language: str


def _parse_compact_number(text: str) -> int:
    value = (text or "").strip().replace(",", "").replace("\u00a0", " ").upper()
    if not value:
        return 0

    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*([KMB]?)", value)
    if not match:
        return 0

    number = float(match.group(1))
    suffix = match.group(2)
    if suffix == "K":
        number *= 1_000
    elif suffix == "M":
        number *= 1_000_000
    elif suffix == "B":
        number *= 1_000_000_000
    return int(number)


class PlaywrightCommentExtractor:
    def __init__(self, headless: bool = True) -> None:
        self.headless = headless

    @staticmethod
    def _accept_youtube_consent(page) -> None:
        if "consent.youtube.com" not in (page.url or ""):
            return

        selectors = [
            "button:has-text('Accept all')",
            "button:has-text('I agree')",
            "button:has-text('Zaakceptuj wszystko')",
            "button:has-text('Akzeptieren')",
            "button:has-text('Accepter tout')",
        ]
        for selector in selectors:
            try:
                btn = page.query_selector(selector)
                if btn:
                    btn.click(timeout=5000)
                    page.wait_for_timeout(1200)
                    return
            except Exception:
                continue

    def list_recent_video_ids(
        self,
        *,
        channel_url: str,
        limit: int = 20,
        content_type: str = "videos",
    ) -> list[str]:
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:  # pragma: no cover - runtime dependency
            raise PlaywrightExtractorError(
                "Playwright is not available. Install dependency and run `playwright install chromium`."
            ) from exc

        if content_type not in {"videos", "shorts"}:
            raise ValueError(f"Unsupported content_type={content_type}. Expected 'videos' or 'shorts'.")

        normalized_url = channel_url.rstrip("/")
        if normalized_url.endswith("/videos") or normalized_url.endswith("/shorts"):
            normalized_url = normalized_url.rsplit("/", 1)[0]
        normalized_url = f"{normalized_url}/{content_type}"

        video_ids: list[str] = []
        seen: set[str] = set()

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=self.headless)
            page = browser.new_page()
            try:
                page.goto(normalized_url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(2000)
                self._accept_youtube_consent(page)
                if "consent.youtube.com" in (page.url or ""):
                    return []
                page.wait_for_timeout(1200)

                for _ in range(8):
                    links = page.query_selector_all("a[href*='/watch?v=']")
                    for link in links:
                        href = link.get_attribute("href") or ""
                        match = re.search(r"v=([A-Za-z0-9_-]{11})", href)
                        if not match:
                            continue
                        vid = match.group(1)
                        if vid in seen:
                            continue
                        seen.add(vid)
                        video_ids.append(vid)
                        if len(video_ids) >= limit:
                            return video_ids
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    page.wait_for_timeout(900)
            except Exception as exc:
                raise PlaywrightExtractorError(
                    f"Failed Playwright channel discovery for {channel_url}: {exc}"
                ) from exc
            finally:
                browser.close()

        return video_ids

    def _extract_comments_via_youtubei(self, page, limit: int) -> list[WebComment]:
        payload = page.evaluate(
            """
            async ({ limit }) => {
              const runsToText = (node) => {
                if (!node) return "";
                if (typeof node.simpleText === "string") return node.simpleText;
                if (Array.isArray(node.runs)) return node.runs.map(r => r.text || "").join("");
                return "";
              };

              const findFirstContinuationToken = (root) => {
                const stack = [root];
                const seen = new Set();
                while (stack.length) {
                  const cur = stack.pop();
                  if (!cur || typeof cur !== "object") continue;
                  if (seen.has(cur)) continue;
                  seen.add(cur);

                  if (cur.continuationCommand && cur.continuationCommand.token) {
                    return cur.continuationCommand.token;
                  }
                  if (cur.nextContinuationData && cur.nextContinuationData.continuation) {
                    return cur.nextContinuationData.continuation;
                  }
                  if (cur.reloadContinuationData && cur.reloadContinuationData.continuation) {
                    return cur.reloadContinuationData.continuation;
                  }

                  for (const v of Object.values(cur)) {
                    if (v && typeof v === "object") stack.push(v);
                  }
                }
                return "";
              };

              const extractContinuationItems = (resp) => {
                const items = [];
                const pushFromEndpoint = (ep) => {
                  const a = ep?.reloadContinuationItemsCommand?.continuationItems;
                  if (Array.isArray(a)) items.push(...a);
                  const b = ep?.appendContinuationItemsAction?.continuationItems;
                  if (Array.isArray(b)) items.push(...b);
                };

                for (const ep of resp?.onResponseReceivedEndpoints || []) pushFromEndpoint(ep);
                for (const ep of resp?.onResponseReceivedActions || []) pushFromEndpoint(ep);

                const cc = resp?.continuationContents?.itemSectionContinuation;
                if (Array.isArray(cc?.contents)) items.push(...cc.contents);
                return items;
              };

              const getNextTokenFromItems = (items) => {
                for (const item of items || []) {
                  const token = item?.continuationItemRenderer?.continuationEndpoint?.continuationCommand?.token;
                  if (token) return token;
                }
                return "";
              };

              const parseThread = (thread) => {
                const renderer = thread?.commentThreadRenderer?.comment?.commentRenderer;
                if (!renderer) return null;
                const text = runsToText(renderer.contentText).trim();
                if (!text) return null;

                const commentId = renderer.commentId || "";
                const authorId =
                  renderer?.authorEndpoint?.browseEndpoint?.browseId ||
                  renderer?.authorText?.simpleText ||
                  "";
                const likeText = runsToText(renderer.voteCount) || String(renderer.likeCount || "");
                const published = runsToText(renderer.publishedTimeText);

                const replyText =
                  runsToText(
                    thread?.commentThreadRenderer?.replies?.commentRepliesRenderer?.moreText
                  ) ||
                  runsToText(
                    thread?.commentThreadRenderer?.replies?.commentRepliesRenderer?.viewReplies?.buttonRenderer?.text
                  ) ||
                  "";

                return {
                  comment_id: commentId,
                  raw_commenter_id: authorId,
                  raw_text: text,
                  like_text: likeText,
                  reply_text: replyText,
                  published_at: published,
                  language: "",
                };
              };

              const ytcfgGet = (key, fallback = "") => {
                try {
                  if (window.ytcfg && typeof window.ytcfg.get === "function") {
                    return window.ytcfg.get(key) || fallback;
                  }
                } catch (e) {}
                return fallback;
              };

              const apiKey = ytcfgGet("INNERTUBE_API_KEY", "");
              const clientVersion = ytcfgGet("INNERTUBE_CLIENT_VERSION", "");
              const visitorData = ytcfgGet("VISITOR_DATA", "");
              const hl = ytcfgGet("HL", "en");

              if (!apiKey || !clientVersion) {
                return { comments: [] };
              }

              let continuation = findFirstContinuationToken(window.ytInitialData || {});
              if (!continuation) {
                return { comments: [] };
              }

              const context = {
                client: {
                  clientName: "WEB",
                  clientVersion,
                  hl,
                  visitorData,
                },
              };

              const out = [];
              const seenIds = new Set();
              for (let pageNo = 0; pageNo < 12 && continuation && out.length < limit; pageNo++) {
                const response = await fetch(`https://www.youtube.com/youtubei/v1/next?key=${apiKey}`, {
                  method: "POST",
                  credentials: "include",
                  headers: {
                    "content-type": "application/json",
                    "x-youtube-client-name": "1",
                    "x-youtube-client-version": clientVersion,
                  },
                  body: JSON.stringify({ context, continuation }),
                });

                if (!response.ok) break;
                const json = await response.json();
                const items = extractContinuationItems(json);
                if (!items.length) break;

                for (const item of items) {
                  const parsed = parseThread(item);
                  if (!parsed) continue;
                  const cid = parsed.comment_id || `${parsed.raw_commenter_id}|${parsed.raw_text.slice(0, 64)}`;
                  if (seenIds.has(cid)) continue;
                  seenIds.add(cid);
                  out.push(parsed);
                  if (out.length >= limit) break;
                }

                continuation = getNextTokenFromItems(items);
              }

              return { comments: out };
            }
            """,
            {"limit": max(limit * 4, 80)},
        )

        comments: list[WebComment] = []
        for idx, item in enumerate(payload.get("comments", []) if isinstance(payload, dict) else []):
            raw_text = str(item.get("raw_text", "")).strip()
            if not raw_text:
                continue
            comment_id = str(item.get("comment_id", "")).strip() or f"pw_yti_{idx}"
            raw_commenter_id = str(item.get("raw_commenter_id", "")).strip() or f"unknown_author_{idx}"
            like_count = _parse_compact_number(str(item.get("like_text", "")))
            reply_count = _parse_compact_number(str(item.get("reply_text", "")))
            comments.append(
                WebComment(
                    comment_id=comment_id,
                    raw_commenter_id=raw_commenter_id,
                    raw_text=raw_text,
                    like_count=like_count,
                    reply_count=reply_count,
                    published_at=str(item.get("published_at", "")),
                    language=str(item.get("language", "")),
                )
            )

        return comments[:limit]

    def _extract_comments_from_dom(self, page, limit: int) -> list[WebComment]:
        comments: list[WebComment] = []

        page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.4)")
        page.wait_for_timeout(1500)

        for _ in range(10):
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(1000)

        threads = page.query_selector_all("ytd-comment-thread-renderer")
        if not threads:
            for selector in [
                "ytd-continuation-item-renderer button",
                "ytd-continuation-item-renderer tp-yt-paper-button",
                "button:has-text('Show more')",
                "button:has-text('Pokaż więcej')",
            ]:
                for btn in page.query_selector_all(selector)[:3]:
                    try:
                        btn.click(timeout=2000)
                        page.wait_for_timeout(800)
                    except Exception:
                        continue
            for _ in range(4):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(1000)
            threads = page.query_selector_all("ytd-comment-thread-renderer")

        for idx, thread in enumerate(threads):
            if idx >= max(limit * 4, 50):
                break

            text_el = thread.query_selector("#content-text")
            raw_text = (text_el.inner_text().strip() if text_el else "")
            if not raw_text:
                continue

            author_el = thread.query_selector("#author-text")
            raw_commenter_id = ((author_el.get_attribute("href") or "") if author_el else "") or f"unknown_author_{idx}"

            like_el = thread.query_selector("#vote-count-middle")
            like_text = like_el.inner_text() if like_el else ""
            like_count = _parse_compact_number(like_text)

            reply_el = thread.query_selector("#replies #more-replies")
            reply_text = reply_el.inner_text() if reply_el else ""
            reply_count = _parse_compact_number(reply_text)

            cid = thread.get_attribute("id") or f"pw_comment_{idx}"
            comments.append(
                WebComment(
                    comment_id=cid,
                    raw_commenter_id=raw_commenter_id,
                    raw_text=raw_text,
                    like_count=like_count,
                    reply_count=reply_count,
                    published_at="",
                    language="",
                )
            )

        return comments[:limit]

    @staticmethod
    def _is_comments_disabled(page) -> bool:
        selectors = [
            "ytd-comments-header-renderer #message",
            "ytd-comments #message",
            "yt-formatted-string#message",
        ]
        for selector in selectors:
            try:
                for el in page.query_selector_all(selector):
                    txt = (el.inner_text() or "").strip().lower()
                    if not txt:
                        continue
                    if "comments are turned off" in txt or "komentarze są wyłączone" in txt:
                        return True
            except Exception:
                continue
        return False

    def get_top_level_comments(self, *, video_url: str, limit: int = 20) -> tuple[list[WebComment], str]:
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:  # pragma: no cover - runtime dependency
            raise PlaywrightExtractorError(
                "Playwright is not available. Install dependency and run `playwright install chromium`."
            ) from exc

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=self.headless)
            page = browser.new_page()

            try:
                page.goto(video_url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(2500)
                self._accept_youtube_consent(page)
                if "consent.youtube.com" in (page.url or ""):
                    raise PlaywrightExtractorError("Consent page not bypassed for video URL.")
                page.wait_for_timeout(1200)

                if self._is_comments_disabled(page):
                    return [], "comments_disabled"

                comments = self._extract_comments_via_youtubei(page, limit)
                if not comments:
                    comments = self._extract_comments_from_dom(page, limit)

            except Exception as exc:
                raise PlaywrightExtractorError(f"Failed Playwright extraction for {video_url}: {exc}") from exc
            finally:
                browser.close()

        return comments, "ok"
