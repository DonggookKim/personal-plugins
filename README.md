# Personal Plugins

개인적으로 쓰는 **ChatGPT / Codex Skills, MCP, 외부 개발 에이전트 연동**을 기록하고 실험하는 저장소입니다. 각 연동은 독립적으로 관리하며 MKM 프로젝트 코드를 이 저장소에 복제하지 않습니다.

## 현재 작업

| 작업 | 상태 | 문서 |
| --- | --- | --- |
| GitHub Projects V2 연동 | 연구 | [Issue #1](https://github.com/DonggookKim/personal-plugins/issues/1) |
| Codex → OpenCode 구현 위임 및 모델 비교 | PoC 준비 | [Issue #2](https://github.com/DonggookKim/personal-plugins/issues/2) |

## OpenCode 코딩 모델 벤치마크

**목표:** Codex가 설계·명세·최종 리뷰를 맡고, OpenCode에 연결된 외부 모델이 실제 코드 구현을 담당하는 구조를 검증합니다. **속도보다 정확도와 최종 합격 비용**을 우선합니다.

동일 비교 대상:

| 별칭 | OpenRouter 모델 |
| --- | --- |
| deepseek | DeepSeek V4.1 Flash **1017 스냅샷** |
| glm | GLM-5.3 Flash |
| nemotron | NVIDIA Nemotron 3 Ultra (free) |

공식 모델 ID는 [benchmarks/models.json](benchmarks/models.json)에 고정합니다. 모델 제공 여부·무료 정책·요금은 실행 전에 재확인하세요.

### 사전 준비

- Python 3.11 이상, Git, Codex CLI, OpenCode CLI가 필요합니다.
- OpenCode에서 OpenRouter를 연결합니다: \`opencode\` → \`/connect\` → OpenRouter; \`/models\`에서 각 모델 식별자를 확인합니다.
- API 키는 환경변수 또는 OpenCode 자격증명 저장소에만 보관합니다. **이 공개 저장소에 키·개인 파일·회사 소스·실제 영상 데이터를 올리지 마세요.**
- 무료 Nemotron 엔드포인트는 별도 데이터 사용·요청 제한 정책이 있습니다. **공개 가능한 합성 코드**로만 평가합니다.

### 빠른 실행 (PowerShell / macOS / Linux)

~~~bash
# 네트워크·과금 없음: 동일 시작 작업 폴더만 준비
python scripts/benchmark.py prepare --case stage1 --model deepseek
python scripts/benchmark.py prepare --case stage1 --model glm
python scripts/benchmark.py prepare --case stage1 --model nemotron

# 실제 모델 호출 및 잠재적 과금: 명시적으로 실행할 때만
python scripts/benchmark.py execute --case stage1 --model deepseek

# 모델 호출 없음: 작업 폴더의 변경된 코드를 독립 테스트로 평가
python scripts/benchmark.py evaluate --case stage1 --model deepseek
~~~

2차 문제는 \`--case stage2\`입니다. 실행 전 \`opencode run --help\`와 \`opencode models\`을 확인하세요. 작업자는 \`.runs/<case>/<model>/\`의 별도 작업 폴더에서 실행됩니다. 결과와 모델 응답 로그는 \`.runs/\`에만 저장되며 Git 추적에서 제외됩니다.

**유의:** 이 러너는 비교용 초안입니다. 강제 샌드박스, 네트워크 차단, API 과금 상한을 구현하지 않았습니다. 신뢰 가능한 로컬 환경에서만 실행하세요. 원격 모델이 지시하는 셸 명령을 실행할 수 있으므로 중요 파일이 있는 디렉터리에서 실행하지 마세요.

### 평가

[문제와 평가 규칙](benchmarks/score-detector/README.md) · [Codex Skill](.agents/skills/opencode-benchmark/SKILL.md)

평가할 것: 첫 시도 테스트 통과, 기존 계약 보존, 신규 테스트, 잘못된 코드 수정, 재위임 횟수, 실제 OpenRouter 청구액. OpenCode의 토큰 사용량은 참고치이며 결제 내역과 구분해 기록합니다.

### 참고 구현 / 공식 가이드

- [opencode-delegate-skill](https://github.com/noorbakhsh09/opencode-delegate-skill)
- [Codex to OpenCode 사용자 사례](https://www.reddit.com/r/codex/comments/1u0fk2p/from_codex_to_opencode/)
- [OpenCode CLI](https://opencode.ai/docs/cli/commands) / [OpenCode 모델 선택](https://opencode.ai/docs/models)
- [OpenRouter + OpenCode 가이드](https://github.com/OpenRouterTeam/docs/blob/main/cookbook/coding-agents/opencode-integration.mdx)

**범위:** 이 PR은 실험용 Skill과 과제를 제공합니다. Codex가 모든 구현을 반드시 위임하도록 강제하지 않으며, 아직 실제 모델 호출·비용·성능 측정이 완료되지 않았습니다.
