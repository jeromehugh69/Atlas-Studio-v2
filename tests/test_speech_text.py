from atlas_studio.speech_text import prepare_speech_text


def test_speech_text_keeps_prose_and_removes_technical_noise():
    source = """**Completed** ✅
Open [Analytics](http://localhost:8080/analytics) for the report.
User → Atlas → Forge.
```python
print({"secret": 1})
```
Traceback (most recent call last):
File "app.py", line 10, in run
ConnectionError: [Errno 111] connection refused
Task ID: 0dc43348-739a-4a44-9fd9-36dbdcbe99aa
"""
    spoken = prepare_speech_text(source)
    assert "Completed" in spoken
    assert "Open Analytics for the report" in spoken
    assert "User then Atlas then Forge" in spoken
    for forbidden in ("http", "print", "Traceback", "ConnectionError", "Errno", "0dc43348", "✅", "→", "{"):
        assert forbidden not in spoken


def test_error_only_response_is_not_spoken():
    source = """Local model unavailable: Ollama timed out after 120 seconds.
Traceback (most recent call last):
ConnectionError: [Errno 111] connection refused
"""
    assert prepare_speech_text(source) == ""


def test_inline_error_sentence_is_removed_but_safe_sentences_remain():
    source = "Hello Jerome. Error: HTTP 500 Internal Server Error. Atlas is ready to continue."
    assert prepare_speech_text(source) == "Hello Jerome. Atlas is ready to continue."


if __name__ == "__main__":
    test_speech_text_keeps_prose_and_removes_technical_noise()
    test_error_only_response_is_not_spoken()
    test_inline_error_sentence_is_removed_but_safe_sentences_remain()
