# Agent guidance — personal-plugins

- 목적: 개인용 ChatGPT / Codex Skill, MCP 및 도구 연동의 실험과 문서화.
- 구현이나 외부 API 실행을 지시받지 않았다면 **모델 호출, 결제, 저장소 push/merge를 하지 않는다**.
- 실제 구현 위임은 `.agents/skills/opencode-delegate/SKILL.md`, 모델 비교는 `.agents/skills/opencode-benchmark/SKILL.md`를 따른다. 두 흐름은 `scripts/opencode_delegate.py`를 공통 실행기로 사용한다.
- Codex는 분석·작업 분할·명세·수용 기준·독립 검증·diff 리뷰·검증된 commit 관리를 담당한다. OpenCode는 지정된 worktree의 구현과 worker 테스트만 담당하며 commit, push, merge하지 않는다.
- 구현 단위마다 하나의 기존 PR에 별도 commit을 추가한다. OpenCode 결과를 commit하기 전에 Codex가 Git diff와 관련 테스트를 독립 검증한다.
- 평가자가 가진 독립 테스트를 구현 모델에 노출하지 않는다. 각 모델은 별도 작업 디렉터리를 사용한다.
- GitHub PR은 사용자 승인 전까지 병합하지 않는다. 실제 MKM 기능 변경은 MKM 저장소에서 별도 처리한다.
- 인증 토큰, 비공개 코드, 사용자의 로컬 개인파일, 영상/음성 등은 공개 테스트에 쓰지 않는다.
- 비용과 성공률을 측정하지 않은 상태에서 특정 모델을 '최고' 또는 '최저가'라고 단정하지 않는다.
