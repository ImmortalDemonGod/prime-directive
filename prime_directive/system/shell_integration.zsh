# Prime Directive Shell Integration

# Ensure pd is in PATH or aliased
# Assuming pd is installed via pip/uv and in path, otherwise alias it
# alias pd="uv run pd" # Uncomment if not installed globally

pd() {
    command pd "$@"
}

pd-cd() {
    # Check if the directory starts with pd-
    if [[ "$1" == pd-* ]]; then
        # Extract the repo ID
        local repo_id="${1#pd-}"
        echo "Switching to Prime Directive context: $repo_id"
        pd switch "$repo_id"
        # pd switch handles tmux attachment, so we don't need to do anything else here usually.
        # But if pd switch just sets up state, we might need to attach here.
        # The python implementation of 'switch' executes 'tmux attach', so control is handed over.
    else
        builtin cd "$@"
    fi
}

# Alias cd to pd-cd
alias cd=pd-cd

# Completion for pd command (basic)
_pd_completion() {
    local -a commands
    commands=('list' 'status' 'doctor' 'freeze' 'switch')
    _describe 'command' commands
}
compdef _pd_completion pd
