# arc_env.sh - Source this before using arc.sh
# Usage: source /home/www/arc_stack/arc_env.sh
# Add to ~/.bashrc: source /home/www/arc_stack/arc_env.sh

export ARC_ROOT="/home/www/arc_stack"

# Convenience aliases
alias arc='$ARC_ROOT/arc.sh'
alias arc-logs='tail -f $ARC_ROOT/logs/*.log'
alias arc-status='$ARC_ROOT/arc.sh status'
alias arc-checkup='$ARC_ROOT/arc.sh checkup'

echo "✅ Arc Codex environment loaded. Commands: arc start|stop|restart|status|logs|build|checkup|backup|prune"
