from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from unittest.mock import Mock

import db
from api.files import ensure_upload_size, validate_upload_signature
import api.chats as chats_api
from fastapi import HTTPException
from services import gemini_file_search
from services.market_data import quote_requested, resolve_company
from services.exa_client import classify_source
from services import orchestrator
from services.orchestrator import build_research_plan, needs_web_research


class PlannerTests(unittest.TestCase):
    def test_skips_greetings_and_short_followups(self):
        self.assertFalse(needs_web_research("Thanks!", False))
        self.assertFalse(needs_web_research("Tell me more", False))

    def test_document_only_question_does_not_call_web(self):
        self.assertFalse(needs_web_research("Summarize this uploaded document", True))

    def test_company_question_is_decomposed_into_bounded_checks(self):
        plan = build_research_plan("What are the latest risks facing TCS?", False)
        self.assertEqual(len(plan["web_queries"]), 2)
        self.assertTrue(any("official company disclosures" in query for query in plan["web_queries"]))
        self.assertIn("Check source quality, dates, and disagreement", plan["steps"])

    def test_common_company_names_map_to_structured_quote_symbol(self):
        self.assertEqual(resolve_company("Why did Reliance Industries rise today?"), ("Reliance Industries", "RELIANCE.NS"))
        self.assertIsNone(resolve_company("Why did Example Motors rise today?"))

    def test_structured_quote_is_only_fetched_for_market_price_questions(self):
        self.assertTrue(quote_requested("Why did TCS stock fall today?"))
        self.assertFalse(quote_requested("What are the latest business risks for TCS?"))

    def test_exchange_domains_are_primary_and_issuer_domains_are_conservative(self):
        self.assertEqual(classify_source("https://www.nseindia.com/filings/report.pdf"), "PRIMARY")
        self.assertEqual(classify_source("https://www.tcs.com/content/investor-relations/financial-statements/q3.pdf"), "MEDIUM")

    def test_source_tiers_do_not_trust_spoofed_hostnames_or_titles(self):
        self.assertEqual(classify_source("https://reuters.com.attacker.example/story", "Reuters"), "MEDIUM")
        self.assertEqual(classify_source("https://attacker.example/story", "SEBI filing"), "MEDIUM")
        self.assertEqual(classify_source("https://attacker.example/annual-report"), "MEDIUM")

class PersistenceTests(unittest.TestCase):
    def test_trace_round_trips_in_messages(self):
        with TemporaryDirectory() as temp_dir:
            with patch.object(db, "DB_PATH", Path(temp_dir) / "test.db"):
                db.init_db()
                conversation = db.create_conversation("test")
                trace = [{"label": "Search", "status": "complete", "detail": "3 sources"}]
                db.add_message(conversation["id"], "assistant", "answer", trace=trace)
                self.assertEqual(db.list_messages(conversation["id"])[0]["trace"], trace)

    def test_raw_file_records_are_available_for_cleanup(self):
        with TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            with patch.object(db, "DB_PATH", Path(temp_dir) / "test.db"):
                db.init_db()
                conversation = db.create_conversation("test")
                db.add_file(conversation["id"], "notes.txt", "text/plain", 5, str(Path(temp_dir) / "notes.txt"), "local_only")
                self.assertEqual(db.list_files_raw(conversation["id"])[0]["filename"], "notes.txt")


class UploadTests(unittest.TestCase):
    def test_upload_size_limit_rejects_oversized_payload(self):
        with patch("api.files.MAX_UPLOAD_BYTES", 5):
            with self.assertRaises(HTTPException) as error:
                ensure_upload_size(6)
        self.assertEqual(error.exception.status_code, 413)

    def test_upload_signature_rejects_extension_mismatch(self):
        with TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            destination = Path(temp_dir) / "not-a-pdf.pdf"
            destination.write_bytes(b"plain text")
            with self.assertRaises(HTTPException) as error:
                validate_upload_signature(destination.name, destination)
            self.assertEqual(error.exception.status_code, 400)
            self.assertFalse(destination.exists())

    def test_upload_signature_accepts_pdf_magic_bytes(self):
        with TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            destination = Path(temp_dir) / "report.pdf"
            destination.write_bytes(b"%PDF-1.7\n")
            validate_upload_signature(destination.name, destination)


class OrchestratorTests(unittest.TestCase):
    def test_unindexed_attachments_are_disclosed_to_answer_and_trace(self):
        with TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            with patch.object(db, "DB_PATH", Path(temp_dir) / "test.db"):
                db.init_db()
                conversation = db.create_conversation("documents")
                db.add_file(conversation["id"], "annual-report.pdf", "application/pdf", 100, str(Path(temp_dir) / "report.pdf"), "local_only")
                seen_context = []

                def answer(_history, extra_context=None):
                    seen_context.append(extra_context or "")
                    return "I could not inspect the attached report."

                with patch.object(orchestrator.gemini_file_search, "available", return_value=False), patch.object(orchestrator.groq_client, "chat", side_effect=answer):
                    result = orchestrator.run_turn(conversation["id"], "Summarize this uploaded document")

                assistant = result["assistant"]
                self.assertIn("annual-report.pdf", seen_context[0])
                self.assertTrue(any(step["label"] == "Attached file availability" for step in assistant["trace"]))
                self.assertFalse(any(step["label"].startswith("Exa") for step in assistant["trace"]))

    def test_followup_carries_forward_source_cards_without_searching_again(self):
        with TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            with patch.object(db, "DB_PATH", Path(temp_dir) / "test.db"):
                db.init_db()
                conversation = db.create_conversation("follow-up")
                source = {
                    "title": "Company filing", "url": "https://www.nseindia.com/filing",
                    "source_name": "nseindia.com", "published_date": "2026-10-22",
                    "excerpt": "The company reported its results.", "reliability": "PRIMARY", "why": "fixture",
                }
                with patch.object(orchestrator.exa_client, "search_web", return_value=[source]), patch.object(orchestrator.groq_client, "chat", return_value="Evidence-backed answer [1]."):
                    orchestrator.run_turn(conversation["id"], "What are the latest risks for TCS?")
                    with patch.object(orchestrator.exa_client, "search_web", side_effect=AssertionError("follow-up should not search")):
                        followup = orchestrator.run_turn(conversation["id"], "Tell me more")

                assistant = followup["assistant"]
                self.assertEqual(assistant["citations"][0]["url"], source["url"])
                self.assertTrue(any(step["label"] == "Prior-turn evidence" for step in assistant["trace"]))

    def test_conversation_delete_removes_local_file_and_metadata(self):
        with TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            root = Path(temp_dir)
            with patch.object(db, "DB_PATH", root / "test.db"), patch.object(chats_api, "UPLOAD_DIR", root / "uploads"):
                db.init_db()
                chats_api.UPLOAD_DIR.mkdir()
                conversation = db.create_conversation("delete me")
                local_file = chats_api.UPLOAD_DIR / "file.txt"
                local_file.write_text("private", encoding="utf-8")
                db.add_file(conversation["id"], "file.txt", "text/plain", 7, str(local_file), "local_only")

                result = chats_api.remove_conversation(conversation["id"])

                self.assertEqual(result, {"ok": True})
                self.assertFalse(local_file.exists())
                self.assertIsNone(db.get_conversation(conversation["id"]))

    def test_failed_remote_file_delete_keeps_conversation_for_retry(self):
        with TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            root = Path(temp_dir)
            with patch.object(db, "DB_PATH", root / "test.db"), patch.object(chats_api, "UPLOAD_DIR", root / "uploads"):
                db.init_db()
                conversation = db.create_conversation("retry delete")
                db.add_file(conversation["id"], "file.txt", "text/plain", 7, "", "ready")
                db.update_file(db.list_files(conversation["id"])[0]["id"], gemini_document_name="fileSearchStores/store/documents/doc")
                with patch.object(chats_api.gemini_file_search, "delete_document", side_effect=gemini_file_search.GeminiError("offline")):
                    with self.assertRaises(HTTPException) as error:
                        chats_api.remove_conversation(conversation["id"])
                self.assertEqual(error.exception.status_code, 502)
                self.assertIsNotNone(db.get_conversation(conversation["id"]))

    def test_gemini_document_deletion_uses_store_document_resource_and_force(self):
        response = Mock(status_code=204)
        with patch.object(gemini_file_search, "GEMINI_API_KEY", "test-key"), patch.object(gemini_file_search.httpx, "delete", return_value=response) as delete:
            gemini_file_search.delete_document("fileSearchStores/store/documents/doc")
        self.assertIn("fileSearchStores/store/documents/doc", delete.call_args.args[0])
        self.assertEqual(delete.call_args.kwargs["params"], {"force": "true"})
if __name__ == "__main__":
    unittest.main()
