
### `.github/ISSUE_TEMPLATE/function_task.md`
```md
---
name: Function task
labels: scope:function, type:enhancement
---
## Function
Name: <FUNCTION_NAME>  
Module: <MODULE_PATH>

## Spec
Link: docs/specs/<FUNCTION_NAME>.md

## Prompt
See prompts/templates/function_impl.prompt.md

## Acceptance
- [ ] Implemented per spec
- [ ] Tests added & passing (pytest -q)
- [ ] Logs match spec
- [ ] Changelog updated
