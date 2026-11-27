# The workstation image under the Features of devcontainer.json. Every FROM names a tag and the
# digest it resolved to, so each machine builds the same bytes; Dependabot (docker) proposes the
# updates and `task env:check` refuses a FROM without a digest.
# ShellCheck: the same image as the collection's lint toolchain (devcontainer-features/.devcontainer/Dockerfile).
FROM koalaman/shellcheck:v0.11.0@sha256:61862eba1fcf09a484ebcc6feea46f1782532571a34ed51fedf90dd25f925a8d AS shellcheck
# uv: installs the Python that .python-version names and syncs .venv from uv.lock. CI installs
# this same version (.github/actions/setup-uv reads it from here).
FROM ghcr.io/astral-sh/uv:0.13.10@sha256:a3ea1357342c1a4bf9a0c53a3deb1b55379aefa037338d8113d5771efa01774f AS uv
FROM mcr.microsoft.com/devcontainers/base:2-bookworm@sha256:06701e75787b0b948709e803f95b42cabf37607b1c308c57471d6f0252149d87
COPY --from=shellcheck /bin/shellcheck /usr/local/bin/shellcheck
COPY --from=uv /uv /uvx /usr/local/bin/
# Marks the stockroom workstation: task env:setup and env:check compare this container with the
# definition it was created from only here.
ENV STOCKROOM_WORKSTATION=1
