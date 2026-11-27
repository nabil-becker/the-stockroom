FROM koalaman/shellcheck:v0.11.0@sha256:61862eba1fcf09a484ebcc6feea46f1782532571a34ed51fedf90dd25f925a8d AS shellcheck
FROM mcr.microsoft.com/devcontainers/base:2-trixie@sha256:41ff7ce12ec45f2704f27a6e091831186ad922ec8112e6339425bfefdf5a70f9
COPY --from=shellcheck /bin/shellcheck /usr/local/bin/shellcheck
