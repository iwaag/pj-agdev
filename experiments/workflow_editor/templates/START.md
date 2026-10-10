# Starting the authoring trial

This area: {{AREA}}

1. Start the editor in a terminal and keep it running:

       {{SERVE}}

   Then open {{URL}} in a browser.
2. Open this folder in VS Code and start the IDE agent with this folder as
   its working directory. It reads `AGENTS.md`; Claude Code reaches it
   through `CLAUDE.md`.
3. A first prompt:

   > Create a project in this authoring area for <purpose>. Clarify its
   > intent and goals, establish the repositories it needs, and create one
   > workflow. Make the result available in the editor for me to review and
   > adjust.

The tool is `{{WFE}}` (`{{WFE}} help`). The file contract is {{CONTRACT}}.
Projects are created beneath this folder; nothing has been created yet.
