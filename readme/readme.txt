Plugin for CudaText.
Gives intelligence commands for JavaScript, using Tern engine, http://ternjs.net/

1) Auto-completion (Ctrl+Space)
2) Go-to-definition (item in editor's context menu)
3) Show function/class call-tip (Ctrl+Shift+Space, call-tip is shown at the editor bottom)

First, you must install Node.js engine, then install Tern like this:
  [sudo] npm install tern -g

Lexer name "JavaScript" is set in the file install.inf, you may append names of other JS-based lexers, after comma.


Authors:
- https://github.com/pohmelie/
- Alexey T. (CudaText)
    
License: MIT
