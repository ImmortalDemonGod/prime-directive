# Prime Directive Shell Integration

# Ensure pd is in PATH or aliased
# Assuming pd is installed via pip/uv and in path, otherwise alias it
# alias pd="uv run pd" # Uncomment if not installed globally

pd() {
    command pd "$@"
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
