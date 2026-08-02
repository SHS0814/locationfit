"""Unit tests for Seoul API response parsing, retries and secret masking."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import requests

from src.data.seoul_api import SeoulAPIClient, SeoulAPIError


class FakeResponse:
    """Small requests.Response substitute for deterministic unit tests."""

    def __init__(
        self,
        body: str,
        *,
        status: int = 200,
        content_type: str = "application/json;charset=UTF-8",
        url: str = "http://example.test/masked/json/Service/1/5",
        redirected: bool = False,
    ) -> None:
        self.text = body
        self.content = body.encode("utf-8")
        self.status_code = status
        self.headers = {"Content-Type": content_type}
        self.url = url
        self.history = [object()] if redirected else []


class FakeSession:
    """Return queued responses or raise queued exceptions."""

    def __init__(self, responses: list[FakeResponse | Exception]) -> None:
        self.responses = iter(responses)
        self.calls = 0
        self.request_kwargs: list[dict[str, object]] = []

    def get(self, url: str, **kwargs: object) -> FakeResponse:
        self.calls += 1
        self.request_kwargs.append(kwargs)
        item = next(self.responses)
        if isinstance(item, Exception):
            raise item
        if item.url.startswith("http://example.test"):
            item.url = url
        return item


def success_body(service: str, total: int, rows: list[dict]) -> str:
    import json

    return json.dumps(
        {
            service: {
                "list_total_count": total,
                "RESULT": {"CODE": "INFO-000", "MESSAGE": "OK"},
                "row": rows,
            }
        }
    )


class SeoulAPIClientTests(unittest.TestCase):
    def make_client(self, responses: list[FakeResponse | Exception], **kwargs: object) -> tuple[SeoulAPIClient, FakeSession]:
        session = FakeSession(responses)
        kwargs.setdefault("allow_insecure_http", True)
        client = SeoulAPIClient(
            api_key="unit-test-secret",
            session=session,
            retry_wait=0,
            logger=None,
            **kwargs,
        )
        return client, session

    def test_normal_json_response(self) -> None:
        service = "DemoService"
        client, _ = self.make_client(
            [FakeResponse(success_body(service, 1, [{"STDR_YYQU_CD": "20211"}]))]
        )
        result = client.fetch_page(service)
        self.assertEqual(result.total_count, 1)
        self.assertEqual(result.rows[0]["STDR_YYQU_CD"], "20211")

    def test_plain_http_requires_explicit_opt_in(self) -> None:
        with self.assertRaisesRegex(SeoulAPIError, "--allow-insecure-seoul-http"):
            SeoulAPIClient(api_key="unit-test-secret", logger=None)

    def test_non_official_host_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "공식 호스트"):
            SeoulAPIClient(
                api_key="unit-test-secret",
                base_url="https://example.test",
                logger=None,
            )

    def test_official_https_does_not_require_insecure_opt_in(self) -> None:
        client = SeoulAPIClient(
            api_key="unit-test-secret",
            base_url="https://openapi.seoul.go.kr",
            session=FakeSession([]),
            logger=None,
        )
        self.assertTrue(client.build_url("DemoService", 1, 5).startswith("https://"))

    def test_redirect_is_not_followed(self) -> None:
        client, session = self.make_client([FakeResponse("", status=302)])
        with self.assertRaisesRegex(SeoulAPIError, "리다이렉트"):
            client.fetch_page("DemoService")
        self.assertEqual(session.request_kwargs[0]["allow_redirects"], False)

    def test_paginates_until_total_count(self) -> None:
        service = "DemoService"
        client, _ = self.make_client(
            [
                FakeResponse(success_body(service, 3, [{"id": 1}, {"id": 2}])),
                FakeResponse(success_body(service, 3, [{"id": 3}])),
            ],
            page_size=2,
        )
        result = client.fetch_all(service, progress=None)
        self.assertEqual([row["id"] for row in result.rows], [1, 2, 3])

    def test_empty_response_is_retried_then_succeeds(self) -> None:
        service = "DemoService"
        client, session = self.make_client(
            [FakeResponse(""), FakeResponse(success_body(service, 1, [{"id": 1}]))],
            max_retries=2,
        )
        result = client.fetch_page(service)
        self.assertEqual(result.total_count, 1)
        self.assertEqual(session.calls, 2)

    def test_html_response_has_diagnostics(self) -> None:
        client, session = self.make_client(
            [FakeResponse("<html><title>Proxy error</title></html>", content_type="text/html")],
            max_retries=3,
        )
        with self.assertRaisesRegex(SeoulAPIError, "HTML 오류 응답") as caught:
            client.fetch_page("DemoService")
        self.assertIn("body_preview=", str(caught.exception))
        self.assertEqual(session.calls, 1)

    def test_xml_authentication_error_is_parsed_without_retry(self) -> None:
        xml = "<RESULT><CODE>INFO-100</CODE><MESSAGE>invalid key</MESSAGE></RESULT>"
        client, session = self.make_client(
            [FakeResponse(xml, content_type="application/xml")], max_retries=3
        )
        with self.assertRaisesRegex(SeoulAPIError, "CODE=INFO-100"):
            client.fetch_page("DemoService")
        self.assertEqual(session.calls, 1)

    def test_json_error_response_is_parsed(self) -> None:
        client, session = self.make_client(
            [FakeResponse('{"RESULT":{"CODE":"ERROR-300","MESSAGE":"missing argument"}}')]
        )
        with self.assertRaisesRegex(SeoulAPIError, "ERROR-300"):
            client.fetch_page("DemoService")
        self.assertEqual(session.calls, 1)

    def test_invalid_service_is_not_retried(self) -> None:
        client, session = self.make_client(
            [FakeResponse('{"RESULT":{"CODE":"ERROR-310","MESSAGE":"missing service"}}')],
            max_retries=3,
        )
        with self.assertRaisesRegex(SeoulAPIError, "ERROR-310"):
            client.fetch_page("MissingService")
        self.assertEqual(session.calls, 1)

    def test_http_500_is_retried_then_succeeds(self) -> None:
        service = "DemoService"
        client, session = self.make_client(
            [
                FakeResponse("server down", status=500, content_type="text/plain"),
                FakeResponse(success_body(service, 1, [{"id": 1}])),
            ],
            max_retries=2,
        )
        result = client.fetch_page(service)
        self.assertEqual(result.total_count, 1)
        self.assertEqual(session.calls, 2)

    def test_duplicate_pages_are_rejected(self) -> None:
        service = "DemoService"
        repeated = [{"id": 1}, {"id": 2}]
        client, _ = self.make_client(
            [FakeResponse(success_body(service, 4, repeated)), FakeResponse(success_body(service, 4, repeated))],
            page_size=2,
        )
        with self.assertRaisesRegex(SeoulAPIError, "중복 페이지"):
            client.fetch_all(service, progress=None)

    def test_url_masking_removes_api_key(self) -> None:
        client, _ = self.make_client([])
        raw = client.build_url("DemoService", 1, 5, (20211,))
        masked = client.mask_url(raw)
        self.assertNotIn("unit-test-secret", masked)
        self.assertIn("***MASKED***", masked)

    def test_connection_exception_does_not_leak_api_key(self) -> None:
        error = requests.ConnectionError(
            "failed at http://host/unit-test-secret/json/DemoService/1/5"
        )
        client, _ = self.make_client([error], max_retries=1)
        with self.assertRaises(SeoulAPIError) as caught:
            client.fetch_page("DemoService")
        message = str(caught.exception)
        self.assertNotIn("unit-test-secret", message)
        self.assertIn("***MASKED***", message)

    def test_quarter_path_url_generation(self) -> None:
        client, _ = self.make_client([])
        url = client.build_url("VwsmTrdarStorQq", 1, 5, (20211,))
        self.assertTrue(url.endswith("/json/VwsmTrdarStorQq/1/5/20211"))

    def test_project_env_loading_and_strip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env"
            env_path.write_text("SEOUL_API_KEY=  env-secret  \n", encoding="utf-8")
            with patch.dict(os.environ, {}, clear=True):
                client = SeoulAPIClient(
                    env_path=env_path,
                    allow_insecure_http=True,
                    logger=None,
                )
            self.assertEqual(client.api_key, "env-secret")

    def test_placeholder_key_is_rejected_before_request(self) -> None:
        with self.assertRaisesRegex(SeoulAPIError, "placeholder"):
            SeoulAPIClient(
                api_key="your_seoul_open_data_api_key",
                allow_insecure_http=True,
                logger=None,
            )


if __name__ == "__main__":
    unittest.main()
