from jobseeker_assistant.dotenv import load_dotenv


def test_loads_values_without_overriding_existing(tmp_path):
    f = tmp_path / ".env"
    f.write_text(
        "# comment\n"
        "LLM_PROVIDER=groq\n"
        'LLM_API_KEY="secret value"\n'
        "export LLM_MODEL=llama  # trailing note\n"
        "EMPTY=\n"
        "ALREADY=from-file\n"
        "not a line\n"
    )
    env = {"ALREADY": "from-shell"}
    loaded = load_dotenv(f, env)
    assert env == {
        "ALREADY": "from-shell",
        "LLM_PROVIDER": "groq",
        "LLM_API_KEY": "secret value",
        "LLM_MODEL": "llama",
    }
    assert loaded == ["LLM_PROVIDER", "LLM_API_KEY", "LLM_MODEL"]  # names only, no values


def test_missing_file_is_fine(tmp_path):
    assert load_dotenv(tmp_path / "nope", {}) == []


def test_test_suite_never_reads_the_real_dotenv(tmp_path):
    env = {"JRA_NO_DOTENV": "1"}
    assert load_dotenv(environ=env) == [] and env == {"JRA_NO_DOTENV": "1"}
