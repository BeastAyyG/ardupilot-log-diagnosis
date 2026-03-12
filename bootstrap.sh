#!/bin/bash
set -e

# ArduPilot Log Diagnosis - Bootstrap Script
# Provides one-click setup and common commands

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if we're in a virtual environment
check_venv() {
    if [ -z "$VIRTUAL_ENV" ]; then
        print_warning "Not in a virtual environment. Consider creating one:"
        echo "  python -m venv .venv"
        echo "  source .venv/bin/activate"
        echo ""
    fi
}

# Setup function
cmd_setup() {
    print_status "Setting up ardupilot-log-diagnosis..."
    
    # Create virtual environment if it doesn't exist
    if [ ! -d ".venv" ]; then
        print_status "Creating virtual environment..."
        python3 -m venv .venv
    fi
    
    # Activate virtual environment
    print_status "Activating virtual environment..."
    source .venv/bin/activate
    
    # Upgrade pip
    print_status "Upgrading pip..."
    pip install --upgrade pip
    
    # Install dependencies from pyproject.toml
    print_status "Installing dependencies..."
    pip install -e ".[dev]"
    
    print_status "Setup complete!"
    print_status "Run './bootstrap.sh test' to verify installation."
}

# Test function
cmd_test() {
    print_status "Running tests..."
    
    # Activate virtual environment if exists
    if [ -d ".venv" ]; then
        source .venv/bin/activate
    fi
    
    python -m pytest -q "$@"
}

# Lint function
cmd_lint() {
    print_status "Running linter..."
    
    # Activate virtual environment if exists
    if [ -d ".venv" ]; then
        source .venv/bin/activate
    fi
    
    # Check if ruff is installed
    if ! command -v ruff &> /dev/null; then
        print_warning "ruff not found. Installing..."
        pip install ruff
    fi
    
    ruff check src/ tests/ || true
}

# Demo function
cmd_demo() {
    print_status "Running demo..."
    
    # Activate virtual environment if exists
    if [ -d ".venv" ]; then
        source .venv/bin/activate
    fi
    
    python -m src.cli.main demo "$@"
}

# Analyze function
cmd_analyze() {
    print_status "Analyzing log file..."
    
    # Activate virtual environment if exists
    if [ -d ".venv" ]; then
        source .venv/bin/activate
    fi
    
    python -m src.cli.main analyze "$@"
}

# Benchmark function
cmd_benchmark() {
    print_status "Running benchmark..."
    
    # Activate virtual environment if exists
    if [ -d ".venv" ]; then
        source .venv/bin/activate
    fi
    
    python -m src.cli.main benchmark "$@"
}

# Help function
cmd_help() {
    echo "ArduPilot Log Diagnosis - Bootstrap Script"
    echo ""
    echo "Usage: ./bootstrap.sh <command> [options]"
    echo ""
    echo "Commands:"
    echo "  setup          Set up the project (create venv, install dependencies)"
    echo "  test          Run tests"
    echo "  lint          Run linter"
    echo "  demo          Run demo"
    echo "  analyze       Analyze a log file"
    echo "  benchmark     Run benchmark"
    echo "  help          Show this help message"
    echo ""
    echo "Examples:"
    echo "  ./bootstrap.sh setup"
    echo "  ./bootstrap.sh test"
    echo "  ./bootstrap.sh demo"
    echo "  ./bootstrap.sh analyze path/to/log.BIN"
    echo "  ./bootstrap.sh benchmark"
}

# Main script
case "${1:-help}" in
    setup)
        cmd_setup
        ;;
    test)
        shift
        cmd_test "$@"
        ;;
    lint)
        cmd_lint
        ;;
    demo)
        shift
        cmd_demo "$@"
        ;;
    analyze)
        shift
        cmd_analyze "$@"
        ;;
    benchmark)
        shift
        cmd_benchmark "$@"
        ;;
    help|--help|-h)
        cmd_help
        ;;
    *)
        print_error "Unknown command: $1"
        echo ""
        cmd_help
        exit 1
        ;;
esac
