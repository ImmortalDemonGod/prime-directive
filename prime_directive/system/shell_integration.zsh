# Prime Directive Shell Integration

# Ensure pd is in PATH or aliased
# Assuming pd is installed via pip/uv and in path, otherwise alias it
# pd forwards its arguments to the real `pd` command found in PATH.

pd() {
    command pd "$@"
}

# pd_chpwd hooks into directory changes to detect Prime Directive repositories.
# This placeholder performs no action by default (succeeds unconditionally).
# To enable active detection, invoke `pd status --check-current` here (may impact performance).
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

# _pd_completion provides basic tab completion for the `pd` command, suggesting the primary subcommands: list, status, doctor, freeze, and switch.
_pd_completion() {
    local -a commands
    commands=('list' 'status' 'doctor' 'freeze' 'switch')
    _describe 'command' commands
}
compdef _pd_completion pd