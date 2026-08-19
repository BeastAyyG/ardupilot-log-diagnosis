from src.data.expert_label_miner import (
    _extract_expert_diagnosis,
    canonicalize_topic_url,
    extract_label_from_text,
)


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


def test_extract_label_from_text_thrust_loss_and_setup_error():
    assert extract_label_from_text("The root cause is thrust loss after the ESC cut out.") == "thrust_loss"
    assert extract_label_from_text("This was caused by reversed propellers on two motors.") == "setup_error"


def test_extract_label_rejects_negated_or_incidental_failure_terms():
    assert extract_label_from_text("The cause is not exactly a brownout; the board logged until impact.") is None
    assert extract_label_from_text("The release includes radio failsafe changes and new parameters.") is None


def test_expert_miner_rejects_release_topics_and_negated_brownout():
    developer = {"dev"}
    release_topic = {
        "title": "Copter 4.4.0 released",
        "post_stream": {
            "posts": [
                {"username": "dev", "cooked": "The release includes a GPS glitch fix."}
            ]
        },
    }
    assert _extract_expert_diagnosis(release_topic, developer) is None

    incident_topic = {
        "title": "Second flight and a brownout with crash",
        "post_stream": {
            "posts": [
                {
                    "username": "dev",
                    "cooked": "The cause is not exactly a brownout; the board logged until impact.",
                }
            ]
        },
    }
    assert _extract_expert_diagnosis(incident_topic, developer) is None


def test_expert_miner_rejects_developer_call_meeting_topics():
    developer = {"dev"}
    topic = {
        "title": "Dev Call Oct 18 2021",
        "post_stream": {
            "posts": [
                {
                    "username": "dev",
                    "cooked": "The power issue is fixed in the next release.",
                }
            ]
        },
    }
    assert _extract_expert_diagnosis(topic, developer) is None
