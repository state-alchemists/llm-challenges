zrb-llm-evaluator run \
  --models openai:gpt-4o,google:gemini-2.5-flash,google:gemini-3.5-flash,deepseek:deepseek-v4-flash,ollama:gemma4:31b-cloud, \
  --test-cases ./challenges/bug-fix,./challenges/copywriting,./challenges/feature,./challenges/integration-bug,./challenges/refactor,./challenges/research \
  --trials 3 \
  --parallelism 8 \
  --timeout 600 \
  --output-dir ./experiment

zrb chat "Analyze @experiment/ result, provide executive summary and failure analysis, including what probably can be improved in the system prompt, insert your analysis at the top section of  @experiment/report.md"
