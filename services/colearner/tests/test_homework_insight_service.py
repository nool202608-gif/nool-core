from src.services import homework_insight_service


def test_falls_back_to_a_generic_placeholder_when_no_api_key_is_configured(monkeypatch):
    monkeypatch.setattr(homework_insight_service, "openai_client", None)

    result = homework_insight_service.generate_homework_insight(
        topic="Magnetic Effects",
        grade="Grade 10",
        subject="Science",
        mastery_percent=52,
        weak_bloom_level="ANALYZE",
        textbook_context="Some syllabus excerpt.",
    )

    assert result["what_needs_understanding"] == "You need more practice with Magnetic Effects."
    assert result["references"] == [{"title": "Class notes", "subtitle": "Magnetic Effects"}]
    assert result["key_idea_title"] == "Magnetic Effects"
    assert result["connection_prompt"] == "How does Magnetic Effects connect to what you already know?"


def test_falls_back_when_the_llm_call_itself_raises(monkeypatch):
    class _BoomClient:
        class chat:
            class completions:
                @staticmethod
                def create(**_kwargs):
                    raise RuntimeError("upstream exploded")

    monkeypatch.setattr(homework_insight_service, "openai_client", _BoomClient())

    result = homework_insight_service.generate_homework_insight(
        topic="Force and Laws of Motion",
        grade="Grade 10",
        subject="Science",
        mastery_percent=61,
        weak_bloom_level="APPLY",
        textbook_context=None,
    )

    assert result["key_idea_title"] == "Force and Laws of Motion"


def test_uses_a_generic_grounding_note_when_no_textbook_context_is_given(monkeypatch):
    captured = {}

    class _FakeMessage:
        content = (
            '{"what_needs_understanding": "x", "references": [{"title": "t", "subtitle": "s"}], '
            '"key_idea_title": "k", "key_idea_body": "b", "connection_prompt": "c"}'
        )

    class _FakeChoice:
        message = _FakeMessage()

    class _FakeResponse:
        choices = [_FakeChoice()]

    class _FakeClient:
        class chat:
            class completions:
                @staticmethod
                def create(*, model, messages, response_format):
                    captured["prompt"] = messages[-1]["content"]
                    return _FakeResponse()

    monkeypatch.setattr(homework_insight_service, "openai_client", _FakeClient())

    result = homework_insight_service.generate_homework_insight(
        topic="Force and Laws of Motion",
        grade="Grade 10",
        subject="Science",
        mastery_percent=61,
        weak_bloom_level="APPLY",
        textbook_context=None,
    )

    assert result == {
        "what_needs_understanding": "x",
        "references": [{"title": "t", "subtitle": "s"}],
        "key_idea_title": "k",
        "key_idea_body": "b",
        "connection_prompt": "c",
    }
    assert "No specific syllabus excerpt was provided" in captured["prompt"]
