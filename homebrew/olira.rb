class Olira < Formula
  desc "Olira AI - CLI for authenticating and configuring MCP access"
  homepage "https://olira.ai"
  version "0.3.0"
  license "MIT"

  on_macos do
    if Hardware::CPU.arm?
      url "https://github.com/olira-ai/olira-cli/releases/download/olira-cli-v#{version}/olira-macos-arm64"
      sha256 "PLACEHOLDER_ARM64_SHA256"

      def install
        bin.install "olira-macos-arm64" => "olira"
      end
    else
      url "https://github.com/olira-ai/olira-cli/releases/download/olira-cli-v#{version}/olira-macos-x86_64"
      sha256 "PLACEHOLDER_X86_64_SHA256"

      def install
        bin.install "olira-macos-x86_64" => "olira"
      end
    end
  end

  on_linux do
    url "https://github.com/olira-ai/olira-cli/releases/download/olira-cli-v#{version}/olira-linux-x86_64"
    sha256 "PLACEHOLDER_LINUX_X86_64_SHA256"

    def install
      bin.install "olira-linux-x86_64" => "olira"
    end
  end

  test do
    assert_match version.to_s, shell_output("#{bin}/olira --version")
  end
end
