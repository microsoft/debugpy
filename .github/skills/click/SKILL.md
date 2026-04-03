---
name: click
description: Best practices for building CLI applications with Click including commands, groups, options, and testing.
---

# Skill: Click

Best practices for building CLI applications with Click including commands, groups, options, and testing.

## When to Use

Apply this skill when building command-line interfaces with Click — commands, groups, options, arguments, and prompts.

## Commands

-   Use `@click.command()` for single commands, `@click.group()` for multi-command CLIs.
-   Declare options with `@click.option()` and positional args with `@click.argument()`.
-   Use `help=` on every option and command for auto-generated help text.
-   Use `envvar=` to allow environment variable fallback for sensitive options.

## Groups

-   Organize subcommands with `@click.group()` and `group.add_command()`.
-   Use `@click.pass_context` to share state between group and subcommands.

## Type Safety

-   Use Click's built-in types (`click.Path(exists=True)`, `click.Choice([...])`, `click.IntRange()`).
-   Use callbacks for custom validation.

## Testing

-   Use `click.testing.CliRunner()` for testing commands without subprocess overhead.
-   Assert on `result.exit_code` and `result.output`.
-   Use `mix_stderr=False` to test stderr separately.

## Pitfalls

-   Don't use `sys.exit()` — use `click.exceptions.Exit` or return from the command.
-   Don't use `print()` — use `click.echo()` for proper encoding handling.
-   Always handle `KeyboardInterrupt` / abort prompts gracefully.

