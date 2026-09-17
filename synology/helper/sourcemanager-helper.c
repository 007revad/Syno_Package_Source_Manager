/*
 * sourcemanager-helper.c
 *
 * Narrow setuid-root launcher for Syno_Package Source Manager.
 * Installed by DSM owner root:<package>, mode 6550 (setuid), from conf/privilege.
 *
 * This replaces the sudoers-based escalation: it does not depend on
 * /usr/bin/sudo being present, and only ever executes one fixed,
 * hardcoded script path with a whitelisted arguments.
 */

#define _GNU_SOURCE
#include <unistd.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

#ifndef TARGET_SCRIPT
#define TARGET_SCRIPT "/var/packages/SourceManager/target/bin/feed_api.sh"
#endif

#define MAX_DELETE_ARGS 16

int main(int argc, char *argv[])
{
    const char *no_arg[]  = { "list", "selfheal", "save", NULL };
    const char *two_arg[] = { "add", NULL };
    const char *var_arg[] = { "delete", NULL };  /* 1..MAX_DELETE_ARGS extra args */

    if (argc < 2) {
        fprintf(stderr, "sourcemanager-helper: missing subcommand\n");
        return 1;
    }
    const char *cmd = argv[1];
    int extra = argc - 2;  /* number of args after the subcommand */

    int is_no_arg = 0, is_two_arg = 0, is_var_arg = 0;
    for (int i = 0; no_arg[i] != NULL; i++)
        if (strcmp(cmd, no_arg[i]) == 0) { is_no_arg = 1; break; }
    for (int i = 0; two_arg[i] != NULL; i++)
        if (strcmp(cmd, two_arg[i]) == 0) { is_two_arg = 1; break; }
    for (int i = 0; var_arg[i] != NULL; i++)
        if (strcmp(cmd, var_arg[i]) == 0) { is_var_arg = 1; break; }

    if (!is_no_arg && !is_two_arg && !is_var_arg) {
        fprintf(stderr, "sourcemanager-helper: rejected unknown subcommand '%s'\n", cmd);
        return 1;
    }
    if (is_no_arg && extra != 0) {
        fprintf(stderr, "sourcemanager-helper: '%s' takes no arguments\n", cmd);
        return 1;
    }
    if (is_two_arg && extra != 2) {
        fprintf(stderr, "sourcemanager-helper: '%s' requires exactly 2 arguments\n", cmd);
        return 1;
    }
    if (is_var_arg && (extra < 1 || extra > MAX_DELETE_ARGS)) {
        fprintf(stderr, "sourcemanager-helper: '%s' requires 1-%d arguments\n", cmd, MAX_DELETE_ARGS);
        return 1;
    }

    /* setuid binary gives us euid=0; promote ruid too so the exec'd
     * script is genuinely root, not just effectively root. */
    if (setuid(0) != 0) {
        perror("sourcemanager-helper: setuid(0) failed");
        return 1;
    }

    /* Sanitize environment: fixed PATH, no inherited surprises. */
    if (clearenv() != 0) {
        fprintf(stderr, "sourcemanager-helper: clearenv failed\n");
        return 1;
    }
    setenv("PATH", "/usr/bin:/bin:/usr/sbin:/sbin:/usr/syno/bin:/usr/syno/sbin", 1);
    setenv("HOME", "/root", 1);

    /* Build argv for execv: TARGET_SCRIPT, cmd, [any extra args], NULL */
    char *exec_argv[3 + MAX_DELETE_ARGS];
    int n = 0;
    exec_argv[n++] = TARGET_SCRIPT;
    exec_argv[n++] = (char *)cmd;
    for (int i = 2; i < argc; i++)
        exec_argv[n++] = argv[i];
    exec_argv[n] = NULL;

    execv(TARGET_SCRIPT, exec_argv);

    perror("sourcemanager-helper: execv failed");
    return 1;
}