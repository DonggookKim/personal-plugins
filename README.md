# Personal Plugins

개인적으로 쓰는 ChatGPT/Codex Skill, MCP, 외부 개발 에이전트 연동을 기록하고 실험하는 저장소입니다. MKM 등 실제 프로젝트 코드는 이 저장소에 복제하지 않습니다.

## Codex → OpenCode 역할 분담

- Codex: 저장소 분석, 작업 분할, 상세 명세, 수용 기준, 독립 테스트, diff 리뷰, 검증된 commit 관리
- OpenCode: 지정된 worktree에서 파일 수정, worker 테스트, 구현 결과 보고
- 사용자: 외부 모델 호출/과금과 최종 통합·병합 결정

범용 구현 위임은 [opencode-delegate Skill](.agents/skills/opencode-delegate/SKILL.md), 동일 조건 모델 비교는 [opencode-benchmark Skill](.agents/skills/opencode-benchmark/SKILL.md)을 사용합니다. 두 Skill은 `scripts/opencode_delegate.py`를 공통 실행기로 사용하므로 별도 Skill 엔진이나 중복 OpenCode 호출 코드가 없습니다.

## 채택한 공개 구현

[noorbakhsh09/opencode-delegate-skill](https://github.com/noorbakhsh09/opencode-delegate-skill)의 MIT 라이선스 구조를 채택했습니다. Codex가 JSON 명세를 만들고 단일 Python 래퍼로 OpenCode를 실행한 뒤 diff와 테스트를 검토하는 흐름이 이 저장소의 목적에 가장 가깝고, Python 외 런타임 의존성이 없습니다. 수정된 코드의 고지는 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)에 있습니다.

검토했지만 함께 설치하지 않은 구현:

- [shinpr/sub-agents-skills](https://github.com/shinpr/sub-agents-skills): MIT, 여러 CLI/모델을 포괄하는 훌륭한 범용 러너이지만 OpenCode 전용 위임과 기능이 중복됩니다.
- [jrzmurray/opencode-dispatch](https://github.com/jrzmurray/opencode-dispatch): persistent server, 세션, Node 기반 worktree 수명주기가 필요한 대규모 병렬 작업에 유용하지만 현재 범위보다 복잡하고 저장소 루트에서 명시적 라이선스 파일을 확인하지 못해 코드를 재사용하지 않았습니다.

## 설치 및 환경 확인

필수 도구는 Git, Python 3.11+, Codex CLI, OpenCode CLI입니다. Codex와 OpenCode는 같은 OS와 파일시스템에서 대상 worktree를 열 수 있어야 합니다. Windows용 OpenCode만 설치되어 있고 Codex가 WSL에서 실행된다면, WSL에도 실행 가능한 OpenCode를 두거나 Windows worktree/실행기로 통일해야 합니다. 재설치 전에 다음을 확인합니다.

```bash
git --version
python --version
codex --version
opencode --version
opencode run --help
opencode models
gh auth status
```

`opencode models`에서 프로젝트에 활성화된 provider/model ID를 확인합니다. OpenRouter 연결은 OpenCode의 `/connect`에서 설정하며 키는 OpenCode 자격증명 저장소나 환경변수에만 둡니다. 키, auth 파일, 비공개 소스, 개인 데이터는 task JSON, 로그, Git, PR에 넣지 않습니다.

저장소의 `.agents/skills/<name>/SKILL.md`는 repo-scoped Skill 경로입니다. 이 저장소 루트에서 새 Codex 세션을 시작하면 발견할 수 있습니다. 전역 설치가 필요하면 검토 후 해당 Skill 디렉터리를 개인 Skill 경로로 복사하되, 이 저장소의 공통 스크립트 경로도 함께 조정해야 합니다.

## 실제 프로젝트 구현 위임

먼저 전용 worktree를 만들고 Codex가 다음 필드를 가진 task JSON을 작성합니다: `objective`, `scope`, 선택적 `allowed_paths`, `constraints`, `acceptance_criteria`, `tests`. 명령과 명세만 확인하는 dry-run은 네트워크와 모델 호출을 하지 않습니다.

```bash
python scripts/opencode_delegate.py \
  --cwd /absolute/path/to/worktree \
  --task-file /mnt/d/CodexTemp/WSL/task.json \
  --model openrouter/z-ai/glm-5.3-flash \
  --dry-run
```

실제 호출은 사용자가 provider 비용과 데이터 정책을 확인한 뒤 실행합니다. 로그 디렉터리는 worktree 밖에 두고 재시도마다 새 번호를 사용합니다.

```bash
python scripts/opencode_delegate.py \
  --cwd /absolute/path/to/worktree \
  --task-file /mnt/d/CodexTemp/WSL/task.json \
  --output-dir /mnt/d/CodexTemp/WSL/opencode-runs/task-001/attempt-001 \
  --model openrouter/z-ai/glm-5.3-flash \
  --timeout 1800 \
  --auto
```

`result.json`에는 성공/실패, 변경 파일, 허용 범위 위반, Git HEAD 변경 여부, diff 경로, 후속 테스트, 오류, 세션 ID, 로그 경로 및 조회 가능한 사용량/비용 필드가 기록됩니다. OpenCode 이벤트의 비용은 참고치이며 OpenRouter 청구 내역이 최종 기준입니다. timeout이나 실패 뒤에도 변경과 로그는 남고, `attempt-002`로 수정 명세를 재위임할 수 있습니다. OpenCode는 commit/push/merge하지 않습니다.

## 세 모델 벤치마크

모델 ID는 [benchmarks/models.json](benchmarks/models.json) 한 곳에서 관리하며 실행기에 하드코딩하지 않습니다. 2026-11-17 OpenRouter 공개 카탈로그에서 다음 ID와 tool-calling 파라미터를 확인했지만, 이 저장소에서는 아직 실제 OpenCode 호출을 검증하지 않았습니다.

| 별칭 | OpenCode model ID | 요금 상태 |
| --- | --- | --- |
| `deepseek` | `openrouter/deepseek/deepseek-v4.1-flash-1017` | 유료, 실행 전 현재 단가 확인 |
| `glm` | `openrouter/z-ai/glm-5.3-flash` | 유료, 실행 전 현재 단가 확인 |
| `nemotron` | `openrouter/nvidia/nemotron-3-ultra-550b-a55b:free` | 무료 tier, rate limit·데이터 정책 확인 |

각 모델은 같은 starter, prompt, evaluator를 사용합니다. Stage 1은 신규 감지기 구현, Stage 2는 공통 기준 구현에서 reset과 threshold schedule을 확장합니다. 모델별 worker 디렉터리와 로그 디렉터리를 분리하며 evaluator는 worker 디렉터리에 복사하지 않습니다.

```bash
# 모델 호출 없음
python scripts/benchmark.py prepare --case stage1 --model deepseek
python scripts/benchmark.py dry-run --case stage1 --model deepseek

# 실제 모델 호출 및 잠재적 과금
python scripts/benchmark.py execute --case stage1 --model deepseek

# 모델 호출 없음: 독립 unittest 평가
python scripts/benchmark.py evaluate --case stage1 --model deepseek
```

`stage1`을 `stage2`로, 모델 별칭을 `glm` 또는 `nemotron`으로 바꿔 동일하게 실행합니다. `prepare`는 기존 결과를 덮어쓰지 않습니다. 반복 `execute`는 `.runs/logs/<stage>/<model>/001`, `002`처럼 첫 시도와 재작업 증거를 모두 보존합니다. Stage 1과 Stage 2 평가는 별도 `evaluation.json`으로 남고 Codex 리뷰 결과는 PR/commit 기록에 추가합니다.

## 안전 및 한계

- `allowed_paths`는 실행 후 범위 위반을 감지하지만 OS sandbox가 아닙니다. 중요 저장소는 전용 worktree와 제한된 OpenCode 권한을 함께 사용합니다.
- timeout은 비용 상한이 아닙니다. 유료 실행 전 OpenRouter 계정 한도를 별도로 설정합니다.
- 무료 모델에는 비공개·개인·회사 데이터를 보내지 않습니다. provider의 현행 데이터 정책을 실행 직전에 확인합니다.
- 모델이 shell/edit tool을 지원하지 않거나 quota/rate limit로 실패하면 품질 실패가 아니라 통합/가용성 실패로 기록합니다.
- Codex는 OpenCode의 테스트 주장을 신뢰하지 않고 전체 diff와 관련 테스트를 독립 검증한 뒤에만 commit합니다.

벤치마크 계약과 공개 evaluator는 [Score Detector 문서](benchmarks/score-detector/README.md)에 있습니다. 이 PR은 API 호출 없이 준비·명령 생성·격리·평가를 검증하며 모델 성능 우승자를 정하지 않습니다.
