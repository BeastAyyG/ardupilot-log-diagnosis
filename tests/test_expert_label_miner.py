from src.data.expert_label_miner import canonicalize_topic_url, extract_label_from_text


def test_canonicalize_topic_url_discourse_post_link():
    url = "https://discuss.ardupilot.org/t/radio-failsafe-during-operation/101055/4"
    assert canonicalize_topic_url(url) == "https://discuss.ardupilot.org/t/radio-failsafe-during-operation/101055"


def test_canonicalize_topic_url_strips_web_citation_suffix():
    url = "https://discuss.ardupilot.org/t/x/123 [web:21]"
    assert canonicalize_topic_url(url) == "https://discuss.ardupilot.org/t/x/123"


def test_extract_label_from_text_rc_failsafe():
    text = "This is a radio failsafe issue. It was caused by RC signal loss."
    assert extract_label_from_text(text) == "rc_failsafe"


def test_extract_label_from_text_unknown_when_uncertain():
    text = "Maybe this is noise, hard to tell, not sure what caused it."
    assert extract_label_from_text(text) is None
