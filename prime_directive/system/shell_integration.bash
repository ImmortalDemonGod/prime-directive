# Prime Directive Shell Integration — Bash

# pd wraps the real `pd` command and, when the subcommand is "switch" and the
# wrapped command exits with status 88, attempts to attach or switch to a tmux
# session named "pd-<target_repo_id>". It returns the tmux command's exit
# status in that special case; otherwise it returns the wrapped command's exit
# pd wraps the real `pd` command, returning its exit status; if the subcommand is `switch` and the wrapped command exits with 88, it requires `tmux` and will attach to or switch the client to the session named `pd-<target_repo_id>`.

pd() {
    local subcmd="$1"
    local target_repo_id="$2"

    command pd "$@"
    local rc=$?

    if [[ "$subcmd" == "switch" && $rc -eq 88 ]]; then
        if ! command -v tmux >/dev/null 2>&1; then
            echo "pd: tmux is required for 'pd switch' but was not found in PATH. Please install tmux and try again." >&2
            return 1
        fi
        local session_name="pd-${target_repo_id}"
        if [[ -n "$TMUX" ]]; then
            tmux switch-client -t "$session_name"
        else
            tmux attach-session -t "$session_name"
        fi
        return $?
    fi

    return $rc
}

# _pd_completion provides tab-completion for the `pd` command, suggesting the subcommands: list, status, doctor, freeze, switch, dossier, and empire.
_pd_completion() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    local commands="list status doctor freeze switch dossier empire"
    COMPREPLY=( $(compgen -W "$commands" -- "$cur") )
}
complete -F _pd_completion pd
