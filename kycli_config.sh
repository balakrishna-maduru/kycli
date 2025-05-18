# kycli_config.sh
echo "alias kycli='python3 /absolute/path/to/kycli/kycli.py'" >> ~/.zshrc
echo "_kycli_completions() {
  COMPREPLY=( \$(compgen -W \"save getkey delete listkeys exit\" -- \"\${COMP_WORDS[1]}\") )
}
complete -F _kycli_completions kycli" >> ~/.zshrc

source ~/.zshrc
echo "✅ Kycli is now available as a terminal command!"