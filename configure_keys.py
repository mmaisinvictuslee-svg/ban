"""VillageON의 API 키를 이 PC에 한 번 설정합니다. 외부 요청을 보내지 않습니다."""

import ast
import getpass
import json
import os
from pathlib import Path
import sys
import tempfile
import tomllib
import warnings


KEY_LABELS = {
    "ADMIN_API_KEY": "행정안전부 서비스키 (Decoding)",
    "KAKAO_REST_API_KEY": "카카오 REST API 키",
}


class ConfigurationError(Exception):
    """설정값을 포함하지 않는 사용자용 오류입니다."""


def _normalize_values(data, label, reject_other_keys=False):
    if not isinstance(data, dict):
        raise ConfigurationError(f"{label}의 최상위 내용은 키 이름과 문자열 값으로 된 객체여야 합니다.")
    if reject_other_keys and set(data) - set(KEY_LABELS):
        raise ConfigurationError(f"{label}에는 ADMIN_API_KEY와 KAKAO_REST_API_KEY 항목만 사용할 수 있습니다. 기존 파일은 변경하지 않았습니다.")
    result = {}
    for name in KEY_LABELS:
        if name not in data:
            continue
        if not isinstance(data[name], str):
            raise ConfigurationError(f"{label}의 {name} 값은 문자열이어야 합니다. 기존 파일은 변경하지 않았습니다.")
        result[name] = data[name].strip()
    return result


def read_local_json(path):
    try:
        with Path(path).open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return {}
    except (ValueError, UnicodeError):
        raise ConfigurationError(".streamlit/villageon_keys.json 형식이 손상되어 읽을 수 없습니다. 파일을 확인해 주세요. 자동으로 덮어쓰지 않습니다.") from None
    except OSError:
        raise ConfigurationError(".streamlit/villageon_keys.json을 읽을 수 없습니다. 파일 접근 권한을 확인해 주세요. 자동으로 덮어쓰지 않습니다.") from None
    return _normalize_values(data, ".streamlit/villageon_keys.json", reject_other_keys=True)


def _read_toml(path, label):
    try:
        with Path(path).open("rb") as handle:
            data = tomllib.load(handle)
    except FileNotFoundError:
        return {}
    except (ValueError, UnicodeError):
        raise ConfigurationError(f"{label} 형식을 읽을 수 없습니다. 해당 TOML 설정을 먼저 확인해 주세요. 기존 파일은 변경하지 않았습니다.") from None
    except OSError:
        raise ConfigurationError(f"{label}을 읽을 수 없습니다. 접근 권한을 확인해 주세요. 기존 파일은 변경하지 않았습니다.") from None
    return _normalize_values(data, label)


def read_code_keys(path):
    """app.py를 실행하지 않고, 두 키의 최상위 문자열 리터럴 할당만 읽습니다."""
    try:
        source = Path(path).read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return {}
    except (OSError, UnicodeError):
        raise ConfigurationError("app.py를 읽을 수 없습니다. 파일의 접근 권한과 UTF-8 저장 형식을 확인해 주세요.") from None
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        # SyntaxError에는 키를 붙여넣은 소스 줄이 포함될 수 있으므로 원문을 출력하지 않습니다.
        raise ConfigurationError("app.py의 파이썬 문법을 확인해 주세요. API 키는 지정한 두 변수의 따옴표 안에 넣고 파일을 저장해야 합니다.") from None
    values = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = node.targets
            value = node.value
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
            value = node.value
        elif isinstance(node, ast.AugAssign):
            # 뒤에서 계산식으로 변경한 변수는 이전 문자열을 확정된 값으로 사용하지 않습니다.
            targets = [node.target]
            value = None
        else:
            continue
        for target in targets:
            if not isinstance(target, ast.Name) or target.id not in KEY_LABELS:
                continue
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                values[target.id] = value.value.strip()
            else:
                # 함수 호출·환경변수 표현식 등을 평가하지 않습니다.
                values.pop(target.id, None)
    return {name: value for name, value in values.items() if value}


def load_configuration(app_dir, home_dir=None, environ=None):
    app_dir = Path(app_dir)
    home_dir = Path.home() if home_dir is None else Path(home_dir)
    environ = os.environ if environ is None else environ
    local_path = app_dir / ".streamlit" / "villageon_keys.json"
    code_values = read_code_keys(app_dir / "app.py")
    if all(code_values.get(name) for name in KEY_LABELS):
        # 두 직접 설정만으로 준비됐으면 사용하지 않을 다른 파일을 읽거나 변경하지 않습니다.
        return {
            "path": local_path, "local_values": {}, "higher_values": dict(code_values),
            "effective": dict(code_values), "sources": {name: "app.py 직접 설정" for name in code_values},
        }
    # 손상된 기존 파일은 상위 설정이 있더라도 자동으로 무시하거나 덮어쓰지 않습니다.
    local_values = read_local_json(local_path)
    global_values = _read_toml(home_dir / ".streamlit" / "secrets.toml", "사용자 공통 ~/.streamlit/secrets.toml")
    project_values = _read_toml(app_dir / ".streamlit" / "secrets.toml", "프로젝트 .streamlit/secrets.toml")
    environment = _normalize_values({name: environ[name] for name in KEY_LABELS if name in environ}, "환경변수")
    effective, higher_values, sources = {}, {}, {}
    for name in KEY_LABELS:
        if code_values.get(name):
            higher_values[name], sources[name] = code_values[name], "app.py 직접 설정"
            effective[name] = code_values[name]
            continue
        # Streamlit은 프로젝트의 명시적 빈 값도 공통 설정 위에 덮어씁니다.
        if name in project_values:
            secret_value, source = project_values[name], "프로젝트 secrets.toml"
        else:
            secret_value, source = global_values.get(name, ""), "사용자 공통 secrets.toml"
        if secret_value:
            higher_values[name], sources[name] = secret_value, source
        elif environment.get(name):
            higher_values[name], sources[name] = environment[name], "환경변수"
        if name in higher_values:
            effective[name] = higher_values[name]
        elif local_values.get(name):
            effective[name], sources[name] = local_values[name], "이 PC의 JSON 설정"
    return {"path": local_path, "local_values": local_values, "higher_values": higher_values,
            "effective": effective, "sources": sources}


def save_json_atomic(path, values):
    """새 파일을 완전히 쓴 후 한 번에 교체합니다. 교체 전 실패 시 기존 파일을 보존합니다."""
    path = Path(path)
    cleaned = _normalize_values(values, "저장할 설정", reject_other_keys=True)
    temporary_path = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".villageon_keys-", suffix=".tmp", delete=False) as handle:
            temporary_path = Path(handle.name)
            try:
                os.chmod(temporary_path, 0o600)
            except OSError:
                pass  # Windows 파일 권한은 운영체제의 접근 권한 설정을 따릅니다.
            json.dump(cleaned, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    except OSError:
        raise ConfigurationError("API 키 설정 파일을 저장하지 못했습니다. 앱 폴더의 쓰기 권한을 확인해 주세요. 기존 설정 파일은 변경하지 않았습니다.") from None
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass


def _hidden_input(prompt):
    try:
        with warnings.catch_warnings():
            # 숨김 입력이 불가능할 때 평문 입력으로 바뀌지 않도록 중단합니다.
            warnings.simplefilter("error", getpass.GetPassWarning)
            return getpass.getpass(prompt)
    except getpass.GetPassWarning:
        raise ConfigurationError("키를 가린 채 입력할 수 있는 터미널이 필요합니다. Windows에서 setup_api_keys.bat를 실행해 주세요.") from None
    except EOFError:
        raise ConfigurationError("터미널 입력이 종료되어 설정을 중단했습니다. 기존 설정 파일은 변경하지 않았습니다.") from None


def main(argv=None, app_dir=None, home_dir=None, environ=None, input_func=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv in (["--help"], ["-h"]):
        print("사용법: python configure_keys.py [--check]")
        print("--check는 두 API 키의 설정 상태만 확인합니다. 실제 API 인증 요청은 보내지 않습니다.")
        print("app.py의 ADMIN_API_KEY와 KAKAO_REST_API_KEY 문자열에 키를 넣었다면 그 설정을 우선 사용합니다.")
        return 0
    if argv not in ([], ["--check"]):
        print("지원하는 옵션은 --check입니다. API 키를 명령어 인수에 넣지 마세요.", file=sys.stderr)
        return 2
    app_dir = Path(__file__).resolve().parent if app_dir is None else Path(app_dir)
    input_func = _hidden_input if input_func is None else input_func
    try:
        config = load_configuration(app_dir, home_dir, environ)
        if argv == ["--check"]:
            if all(config["effective"].get(name) for name in KEY_LABELS):
                print("API 키 두 항목의 설정이 있습니다. 설정 상태 확인이며 실제 인증 성공 여부는 앱에서 확인합니다.")
                return 0
            print("API 키 설정이 아직 모두 준비되지 않았습니다. 실제 인증 검사는 수행하지 않았습니다.")
            return 1
        print("VillageON API 키 1회 설정")
        print("입력한 값은 화면에 표시되지 않습니다. 붙여넣은 뒤 Enter를 누르세요.")
        print("이 도우미에서 새로 입력한 키는 앱 폴더의 .streamlit/villageon_keys.json에 저장합니다. 암호화된 파일은 아닙니다.")
        print("app.py에 직접 설정한 키는 우선 사용하며 다시 입력받거나 JSON으로 복사하지 않습니다.")
        updated = dict(config["local_values"])
        for name, label in KEY_LABELS.items():
            if config["higher_values"].get(name):
                print(f"{label}: {config['sources'][name]} 설정을 사용하므로 입력을 생략합니다.")
                continue
            suffix = " (이 PC에 저장된 값이 있습니다. Enter: 그대로 유지)" if updated.get(name) else ""
            entered = input_func(f"{label}{suffix}: ")
            entered = _normalize_values({name: entered}, "입력값")[name]
            if entered:
                updated[name] = entered
        effective = {**updated, **config["higher_values"]}
        missing = [KEY_LABELS[name] for name in KEY_LABELS if not effective.get(name)]
        if missing:
            print("아직 입력하지 않은 항목: " + ", ".join(missing))
            print("두 항목이 준비되지 않아 저장하지 않았습니다. 기존 설정 파일은 그대로 유지됩니다.")
            return 1
        if updated != config["local_values"]:
            save_json_atomic(config["path"], updated)
            print("API 키 입력을 저장했습니다. 다음 실행부터 이 PC의 설정을 사용합니다.")
        else:
            print("기존 API 키 설정을 그대로 사용합니다. 파일을 변경하지 않았습니다.")
        print("저장·설정 상태만 확인했습니다. 실제 API 인증과 연결 결과는 앱에서 확인해 주세요.")
        return 0
    except KeyboardInterrupt:
        print("\n설정을 취소했습니다. 저장 단계 전이라면 기존 파일을 그대로 유지합니다.")
        return 130
    except ConfigurationError as exc:
        print(f"[설정 오류] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
