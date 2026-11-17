# Personal Plugins

개인적으로 쓰는 ChatGPT/Codex Skill, MCP, 외부 개발 에이전트 연동을 기록하고 실험하는 저장소입니다. MKM 등 실제 프로젝트 코드는 이 저장소에 복제하지 않습니다.

## Codex → OpenCode 역할 분담

- Codex: 저장소 분석, 작업 분할, 상세 명세, 수용 기준, 독립 테스트, diff 리뷰, 검증된 commit 관리
- OpenCode: 지정된 작업 디렉터리에서 파일 수정, worker 테스트, 구현 결과 보고
- 사용자: 외부 모델 호출/과금과 최종 통합·병합 결정

일반 구현 위임은 설치된 upstream `$opencode-delegate` Skill을 사용합니다. 이 저장소의 [opencode-benchmark Skill](.agents/skills/opencode-benchmark/SKILL.md)은 같은 upstream runner를 호출해 모델 비교에 필요한 격리, numbered attempts, 로그, diff, 독립 평가만 추가합니다. 별도 OpenCode 실행 엔진을 복제하지 않습니다.

## 공개 Skill 선택

채택: [noorbakhsh09/opencode-delegate-skill](https://github.com/noorbakhsh09/opencode-delegate-skill)

- MIT 라이선스, Python 표준 라이브러리만 사용
- Codex가 JSON 명세를 만들고 `run_worker.py`가 `opencode run`을 blocking 방식으로 실행
- `--model`, `--timeout`, `--auto`, `--dry-run` 지원
- Codex가 실행 후 Git diff와 테스트를 독립 검증하는 역할 분리

함께 설치하지 않은 구현:

- [shinpr/sub-agents-skills](https://github.com/shinpr/sub-agents-skills): MIT, OpenCode를 포함한 여러 CLI와 권한/streaming/timeout을 지원하지만 현재 OpenCode 전용 흐름과 중복됩니다.
- [jrzmurray/opencode-dispatch](https://github.com/jrzmurray/opencode-dispatch): persistent server, session resume, worktree 수명주기가 필요한 대규모 병렬 작업에 적합하지만 Node 기반 구성 전체가 현재 범위보다 복잡하고 저장소 루트에서 명시적 LICENSE 파일을 확인하지 못했습니다.

현재 upstream Skill은 one-shot 실행입니다. OpenCode CLI 자체의 `--continue`/`--session` 기능을 runner가 노출하지 않으므로 실패 수정은 새 명세와 numbered attempt로 보존합니다. 실제 장기 세션 재개가 필요해질 때만 위 두 구현을 다시 평가합니다.

## 설치 및 현재 환경

Skill 설치 경로:

```text
~/.agents/skills/opencode-delegate/
├── SKILL.md
└── scripts/run_worker.py
```

현재 설치는 upstream Git checkout이며 Codex에서 `$opencode-delegate`로 인식됩니다. 처음 설치한 직후 Skill이 보이지 않는 기존 Codex 세션은 재시작하거나 새 세션을 열어야 합니다. 이미 설치되어 있다면 재설치하거나 인증을 초기화하지 않습니다.

새 환경에 동일한 upstream을 설치할 때만 다음을 사용합니다.

```bash
git clone https://github.com/noorbakhsh09/opencode-delegate-skill.git \
  ~/.agents/skills/opencode-delegate
```

2026-11-17 확인 환경:

- WSL2 Ubuntu, Codex CLI `0.169.0`
- OpenCode `v2.3.0`, NVM 경로 `~/.nvm/versions/node/v22.22.2/bin/opencode`
- OpenRouter credential: `opencode auth list`에서 `stored` 확인
- Git/GitHub CLI 정상, PR 저장소 push 권한 확인
- WSL 기본 `python3`은 3.8이며, 벤치마크 계약은 Python 3.11을 요구함. 독립 평가는 Windows Python 3.11에서도 검증함

NVM은 interactive shell에서 로드됩니다. 일반 터미널에서는 `opencode`가 바로 보이지만 비대화형 도구 셸에서는 PATH에 없을 수 있습니다. 벤치마크 러너는 WSL login shell에서도 실행 파일을 찾아 PATH를 전달합니다.

비밀값을 출력하는 `opencode auth export`는 사용하지 않습니다. 상태 확인은 다음으로 충분합니다.

```bash
opencode --version
opencode run --help
opencode auth list
opencode models
```

## 실제 프로젝트 구현 위임

Codex가 다음 형식의 task JSON을 저장소 밖 임시 경로에 작성합니다.

```json
{
  "objective": "구체적인 구현 결과",
  "scope": ["수정 대상과 동작"],
  "constraints": ["기존 계약과 금지 변경"],
  "acceptance_criteria": ["관찰 가능한 완료 조건"],
  "tests": ["python -m unittest tests.test_component -v"]
}
```

모델 호출 없는 검증:

```bash
python3 ~/.agents/skills/opencode-delegate/scripts/run_worker.py \
  --cwd /absolute/path/to/worktree \
  --task-file /mnt/d/CodexTemp/WSL/task.json \
  --model openrouter/z-ai/glm-5.3-flash \
  --dry-run
```

실제 호출은 사용자가 provider 비용과 데이터 정책을 확인한 뒤에만 수행합니다. `run_worker.py`가 완료까지 기다리므로 Codex의 반복 polling은 필요하지 않습니다.

```bash
set -o pipefail
python3 ~/.agents/skills/opencode-delegate/scripts/run_worker.py \
  --cwd /absolute/path/to/worktree \
  --task-file /mnt/d/CodexTemp/WSL/task.json \
  --model openrouter/z-ai/glm-5.3-flash \
  --timeout 1800 \
  --auto 2>&1 | tee /mnt/d/CodexTemp/WSL/opencode-runs/task-001.jsonl
```

OpenCode는 commit/push/merge하지 않습니다. Codex가 전체 diff와 테스트를 독립 검증하고, 문제가 있으면 수정 명세로 재위임한 뒤 검증된 작업 단위만 기존 PR에 commit합니다.

## 세 모델 설정

모델 ID는 [benchmarks/models.json](benchmarks/models.json) 한 곳에서 관리하며 Python 코드에 하드코딩하지 않습니다. 세 ID 모두 현재 `opencode models`의 정확한 항목으로 확인했습니다.

| 별칭 | OpenCode model ID | 상태 |
| --- | --- | --- |
| `deepseek` | `openrouter/deepseek/deepseek-v4.1-flash-1017` | 선택 가능, 이번 작업에서는 호출 안 함 |
| `glm` | `openrouter/z-ai/glm-5.3-flash` | 선택 가능, 이번 작업에서는 호출 안 함 |
| `nemotron` | `openrouter/nvidia/nemotron-3-ultra-550b-a55b:free` | 선택 가능, 이번 작업에서는 호출 안 함 |

가격, rate limit, provider 데이터 정책은 실행 시점에 다시 확인합니다. 무료 모델에도 비공개·개인·회사 데이터를 보내지 않습니다.

## 벤치마크

Stage 1은 점수 변화 감지기 신규 구현, Stage 2는 공통 fixture에서 reset timestamp와 threshold schedule을 확장합니다. 모델별 worker 디렉터리와 attempt 로그를 분리하며 공개 독립 evaluator는 worker 디렉터리에 복사하지 않습니다.

```bash
# 네트워크 추론/모델 호출 없음
python scripts/benchmark.py prepare --case stage1 --model deepseek
python scripts/benchmark.py dry-run --case stage1 --model deepseek

# 실제 모델 호출: 이번 작업에서는 실행하지 않음
python scripts/benchmark.py execute --case stage1 --model deepseek

# 모델 호출 없음: 독립 unittest 평가
python scripts/benchmark.py evaluate --case stage1 --model deepseek
```

`stage1`을 `stage2`로, 모델을 `glm` 또는 `nemotron`으로 바꿔 같은 조건으로 실행합니다. 반복 `execute`는 `.runs/logs/<stage>/<model>/001`, `002`처럼 첫 시도와 수정 결과를 분리합니다. 각 `result.json`에는 모델 ID, 실행 시간, 변경 파일, 범위 위반, worker 테스트, 세션 ID와 조회 가능한 usage/cost 필드가 기록됩니다. provider 청구 내역이 최종 비용 기준입니다.

## 안전 및 한계

- 모델 실행 전 clean worktree와 작업 범위를 확인합니다. benchmark의 `allowed_paths`는 사후 검증이며 OS sandbox가 아닙니다.
- timeout은 비용 상한이 아닙니다. 유료 실행 전 OpenRouter account limit를 별도로 설정합니다.
- worker 테스트 주장만으로 합격 처리하지 않고 독립 evaluator와 Codex 리뷰를 모두 수행합니다.
- API/auth/quota/rate-limit 실패는 코드 품질 실패와 분리합니다.
- 벤치마크 완료 전 일반적인 모든 Codex 구현에 OpenCode 위임을 강제하지 않습니다.

세부 계약과 evaluator는 [Score Detector 문서](benchmarks/score-detector/README.md)에 있습니다.
