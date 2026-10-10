local M = {}

function M.setup()
  local source = debug.getinfo(1, "S").source:sub(2)
  local sender = vim.fn.fnamemodify(
    vim.fn.fnamemodify(source, ":p:h:h") .. "/scripts/tmux-opener-send",
    ":p"
  )

  if vim.fn.executable(sender) ~= 1 then
    return false
  end

  vim.fn.system({ "uv", "run", "--no-project", "--no-sync", "python", sender, "--pdf", "--check-bridge" })
  if vim.v.shell_error ~= 0 then
    return false
  end

  vim.g.vimtex_view_method = "general"
  vim.g.vimtex_view_general_viewer =
    "uv run --no-project --no-sync python " .. vim.fn.shellescape(sender)
  vim.g.vimtex_view_general_options = "--pdf @pdf"
  vim.g.vimtex_view_use_temp_files = true

  local group = vim.api.nvim_create_augroup("tmux_opener_vimtex", { clear = true })
  vim.api.nvim_create_autocmd("User", {
    pattern = "VimtexEventCompileSuccess",
    group = group,
    -- Run after VimTeX has copied its completed PDF snapshot.
    callback = function(args)
      local buffer = args.buf
      vim.schedule(function()
        if not vim.api.nvim_buf_is_valid(buffer) then
          return
        end

        local ok, pdf
        vim.api.nvim_buf_call(buffer, function()
          ok, pdf = pcall(vim.api.nvim_eval, "b:vimtex.compiler.get_file('pdf')")
        end)
        if not ok or type(pdf) ~= "string" or pdf == "" then
          return
        end
        pdf = vim.fn.fnamemodify(pdf, ":p")

        vim.system({
          "uv",
          "run",
          "--no-project",
          "--no-sync",
          "python",
          sender,
          "--pdf",
          "--refresh",
          pdf,
        }, { detach = true }, function(result)
          if result.code == 0 then
            return
          end
          vim.schedule(function()
            vim.notify(
              "tmux-opener VimTeX PDF refresh failed (exit code " .. result.code .. ")",
              vim.log.levels.WARN
            )
          end)
        end)
      end)
    end,
  })

  return true
end

return M
