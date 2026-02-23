#include <unistd.h>
#include <stdlib.h>
#include <stdio.h>

// Trampoline to run the MCP server as the environment user.
//
// The compiled binary will be owned by the environment user and have the setuid
// bit set. This needs to be binary because we can't make the Python MCP server
// (a script) directly setuid.
//
// A setuid binary, when executed, preserves the real UID of the caller, so we
// can use it to determine who launched this MCP server process and distinguish
// between agent and verifier users.

int main(void) {
    setenv("HOME", "/home/environment", 1);
    chdir("/opt/mcp-server");

    char *args[] = {"uv", "run", "python", "server.py", NULL};
    execv("/usr/local/bin/uv", args);

    perror("execv");
    return 1;
}
