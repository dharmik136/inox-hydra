"""
Inox Hydra (LinkedIn Studio Enterprise) Unified CLI
===================================================
Provides command-line management for Bring-Your-Own-AI (BYO-AI) configuration,
system health diagnostics, and background daemon operations.

Usage:
  python studio_cli.py ai configure [--provider PROVIDER] [--api-key KEY] [--model MODEL] [--base-url URL]
  python studio_cli.py ai test
  python studio_cli.py ai status
  python studio_cli.py ai list-providers
  python studio_cli.py ai reset
"""

import sys
import os
import argparse
from datetime import datetime

# Add studio/backend to path
root_dir = os.path.abspath(os.path.dirname(__file__))
backend_dir = os.path.join(root_dir, "studio", "backend")
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from database import get_db, init_db
from agno_agentos.model_gateway import (
    SUPPORTED_PROVIDERS,
    AIProviderConfig,
    verify_ai_connection,
    get_current_ai_config,
    save_ai_config
)


def cmd_list_providers(args):
    """Lists all supported AI providers and models."""
    print("\n=======================================================")
    print("  INOX HYDRA - SUPPORTED AI PROVIDERS & MODELS")
    print("=======================================================\n")
    print(f"{'PROVIDER KEY':<20} {'NAME':<32} {'DEFAULT MODEL':<24} {'REQUIRES KEY'}")
    print("-" * 88)
    for key, info in SUPPORTED_PROVIDERS.items():
        req_key = "Yes" if info["requires_key"] else "No (Offline/Local)"
        print(f"{key:<20} {info['name']:<32} {info['default_model']:<24} {req_key}")
    print("\nTip: Configure a provider with: python studio_cli.py ai configure --provider <key>\n")


def cmd_ai_status(args):
    """Displays the currently active AI configuration."""
    config = get_current_ai_config()
    meta = config.to_dict()

    print("\n=======================================================")
    print("  INOX HYDRA - ACTIVE AI CONFIGURATION")
    print("=======================================================\n")
    print(f"  Provider:       {meta['provider_name']} ({meta['provider']})")
    print(f"  Model:          {meta['model']}")
    print(f"  Base URL:       {meta['base_url'] or '(Default Endpoint)'}")
    print(f"  API Key:        {meta['api_key_masked'] or '(None)'}")
    print(f"  Status:         {meta['status'].upper()}")
    print(f"  Last Verified:  {meta['verified_at'] or 'Never'}")
    print(f"  Image Support:  {'Yes' if meta['supports_images'] else 'Fallback to Pollinations/Local'}")
    print("\n=======================================================\n")


def cmd_ai_test(args):
    """Performs a live connectivity and latency test on the configured AI provider."""
    config = get_current_ai_config()
    print(f"\nPinging configured AI provider: {config.provider} ({config.model})...")

    success, message, latency = verify_ai_connection(
        provider=config.provider,
        api_key=config.api_key,
        model=config.model,
        base_url=config.base_url
    )

    if success:
        print(f"[SUCCESS] {message}")
        print(f"Latency:  {latency} ms")
        print("Status:   CONNECTED & OPERATIONAL\n")
        return 0
    else:
        print(f"[FAILED]  {message}")
        if latency > 0:
            print(f"Latency:  {latency} ms")
        print("Status:   OFFLINE / UNREACHABLE\n")
        return 1


def cmd_ai_configure(args):
    """Configures, validates with live ping, and connects an AI provider."""
    provider = args.provider
    api_key = args.api_key
    model = args.model
    base_url = args.base_url

    # Interactive prompts if provider argument was omitted
    if not provider:
        print("\nAvailable Providers:")
        for idx, (k, v) in enumerate(SUPPORTED_PROVIDERS.items(), 1):
            print(f"  [{idx}] {k} - {v['name']}")
        
        choice = input("\nSelect provider [default: gemini]: ").strip().lower()
        if choice in SUPPORTED_PROVIDERS:
            provider = choice
        elif choice.isdigit() and 1 <= int(choice) <= len(SUPPORTED_PROVIDERS):
            provider = list(SUPPORTED_PROVIDERS.keys())[int(choice) - 1]
        else:
            provider = "gemini"

    if provider not in SUPPORTED_PROVIDERS:
        print(f"\n[ERROR] Unknown provider '{provider}'. Run 'python studio_cli.py ai list-providers' to see options.")
        return 1

    prov_meta = SUPPORTED_PROVIDERS[provider]

    if prov_meta["requires_key"] and not api_key:
        api_key = input(f"Enter API Key for {prov_meta['name']}: ").strip()
        if not api_key:
            print("[ERROR] API key is required for this provider.")
            return 1

    if not model:
        if not args.provider:
            default_model = prov_meta["default_model"]
            custom_model = input(f"Enter model name [default: {default_model}]: ").strip()
            model = custom_model if custom_model else default_model
        else:
            model = prov_meta["default_model"]

    if not base_url and provider in ("ollama", "custom_openai"):
        if not args.provider:
            default_url = prov_meta["default_base_url"]
            custom_url = input(f"Enter Base URL [default: {default_url}]: ").strip()
            base_url = custom_url if custom_url else default_url
        else:
            base_url = prov_meta["default_base_url"]

    print(f"\nVerifying connection to {prov_meta['name']} ({model})...")

    # Step 1: Active Connection Verification Ping
    success, message, latency = verify_ai_connection(
        provider=provider,
        api_key=api_key,
        model=model,
        base_url=base_url
    )

    if not success:
        print("\n-------------------------------------------------------")
        print(f"[VERIFICATION FAILED] Could not connect to {prov_meta['name']}:")
        print(f"Error: {message}")
        print("-------------------------------------------------------")
        print("Configuration was NOT saved. Please check credentials or network and try again.\n")
        return 1

    # Step 2: Save to SQLite
    config = AIProviderConfig(
        provider=provider,
        api_key=api_key,
        model=model,
        base_url=base_url,
        verified_at=datetime.now().isoformat(),
        status="active"
    )
    save_ai_config(config)

    print("\n=======================================================")
    print(f"  [SUCCESS] Connected to {prov_meta['name']}!")
    print(f"  Model:    {model}")
    print(f"  Latency:  {latency} ms")
    print(f"  Storage:  Persisted in local SQLite vault (zero telemetry)")
    print("=======================================================")
    print("Inox Hydra workflows will now automatically orchestrate through this model.\n")
    return 0


def cmd_ai_reset(args):
    """Resets AI configuration back to local deterministic zero-egress mode."""
    config = AIProviderConfig(
        provider="local_deterministic",
        api_key="",
        model="deterministic-heuristics-v2",
        base_url=None,
        verified_at=datetime.now().isoformat(),
        status="active"
    )
    save_ai_config(config)
    print("\n[SUCCESS] AI configuration reset to Inox Hydra Local Deterministic Engine (100% Zero-Egress Offline).\n")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Inox Hydra Enterprise CLI - Multi-Model AI Orchestrator & Studio Control",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # AI Subcommands
    ai_parser = subparsers.add_parser("ai", help="Bring-Your-Own-AI (BYO-AI) management")
    ai_subparsers = ai_parser.add_subparsers(dest="ai_command", help="AI actions")

    # ai configure
    config_parser = ai_subparsers.add_parser("configure", help="Configure and test an AI provider")
    config_parser.add_argument("--provider", choices=list(SUPPORTED_PROVIDERS.keys()), help="AI provider name")
    config_parser.add_argument("--api-key", help="API Key for the provider")
    config_parser.add_argument("--model", help="Model name (e.g. gpt-4o, gemini-2.5-flash, claude-3-5-sonnet)")
    config_parser.add_argument("--base-url", help="Base URL for Ollama, vLLM, or custom endpoint")

    # ai test
    ai_subparsers.add_parser("test", help="Test live connection to the configured AI")

    # ai status
    ai_subparsers.add_parser("status", help="Show active AI configuration")

    # ai list-providers
    ai_subparsers.add_parser("list-providers", help="List all supported AI providers and models")

    # ai reset
    ai_subparsers.add_parser("reset", help="Reset to local deterministic zero-egress mode")

    args = parser.parse_args()

    if args.command == "ai":
        if args.ai_command == "configure":
            sys.exit(cmd_ai_configure(args))
        elif args.ai_command == "test":
            sys.exit(cmd_ai_test(args))
        elif args.ai_command == "status":
            sys.exit(cmd_ai_status(args))
        elif args.ai_command == "list-providers":
            sys.exit(cmd_list_providers(args))
        elif args.ai_command == "reset":
            sys.exit(cmd_ai_reset(args))
        else:
            ai_parser.print_help()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
