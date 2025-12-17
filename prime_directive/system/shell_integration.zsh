# Prime Directive Shell Integration

# Ensure pd is in PATH or aliased
# Assuming pd is installed via pip/uv and in path, otherwise alias it
# pd wraps the real `pd` command and, when the subcommand is `switch` and the wrapped command exits with status 88, switches or attaches tmux to the session named `pd-<target_repo_id>`.
# Returns the tmux command's exit status when handling that special `switch` case; otherwise returns the wrapped `pd` command's exit status.

pd() {
    local subcmd="$1"
    local target_repo_id="$2"

    command pd "$@"
    local rc=$?

    if [[ "$subcmd" == "switch" && $rc -eq 88 ]]; then
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

# Hooks into directory changes to detect Prime Directive repositories
pd_chpwd() {
    # This is a placeholder for context detection.
    # To enable auto-detection, we would check if $PWD matches a registered repo.
    # Since invoking python on every cd is slow, we recommend using 'pd switch' explicitly.
    # However, if you want active monitoring, uncomment the line below:
    # pd status --check-current
    true
}

# Register the hook
autoload -Uz add-zsh-hook
add-zsh-hook chpwd pd_chpwd

# Completion for pd command (basic)
_pd_completion() {
    local -a commands
    commands=('list' 'status' 'doctor' 'freeze' 'switch')
    _describe 'command' commands
}
compdef _pd_completion pd