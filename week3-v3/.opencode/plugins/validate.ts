import type { Plugin } from "@opencode-ai/plugin"

const WATCHED_TOOLS = ["write", "edit"]
const ARTICLE_PATTERN = /^knowledge\/articles\/.*\.json$/

export const ValidatePlugin: Plugin = async (input) => {
  const { $ } = input

  return {
    "tool.execute.after": async (hookInput) => {
      const { tool, args } = hookInput

      if (!WATCHED_TOOLS.includes(tool)) {
        return
      }

      const filePath = args?.file_path || args?.filePath
      if (!filePath || typeof filePath !== "string") {
        return
      }

      if (!ARTICLE_PATTERN.test(filePath)) {
        return
      }

      try {
        const result = await $`python3 hooks/validate_json.py ${filePath}`.nothrow()

        if (result.exitCode !== 0) {
          console.error(`[validate] Validation failed for ${filePath}:`)
          console.error(result.stderr.toString())
        } else {
          console.log(`[validate] ${filePath} passed validation`)
        }
      } catch (error) {
        console.error(`[validate] Shell execution error:`, error)
      }
    },
  }
}
