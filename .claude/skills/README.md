# Vendored skills

아래 5개 스킬은 [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills)에서 복사했습니다.

- 출처 커밋: `e997ac5b9a74eab332d5e9793bb38a38c8cfdd74` (2026-11-23)
- 라이선스: MIT (`LICENSE-agent-skills`)
- 수정 없이 원본 그대로 둡니다. 갱신할 때는 같은 경로로 다시 복사하고 위 커밋 해시를 바꿉니다.

| 스킬 | 이 저장소에서 쓰는 곳 |
|---|---|
| `context-engineering` | `CLAUDE.md`와 `context/latest.md`(프롬프트 주입 블록) 설계 |
| `test-driven-development` | 수집기·스코어링 변경 시 실패 테스트 먼저 작성 |
| `source-driven-development` | X / YouTube / pytrends API 동작을 공식 문서로 확인 |
| `ci-cd-and-automation` | `.github/workflows/context.yml` 품질 게이트 |
| `debugging-and-error-recovery` | 대체 데이터 비율 급증, Actions 실패 원인 추적 |

나머지 21개 스킬과 `/spec` `/plan` `/build` `/test` `/review` `/ship` 커맨드는 플러그인으로 설치합니다.
`.claude/settings.json`에 마켓플레이스가 등록돼 있으므로 Claude Code에서 아래 한 줄이면 됩니다.

```
/plugin install agent-skills@addy-agent-skills
```
