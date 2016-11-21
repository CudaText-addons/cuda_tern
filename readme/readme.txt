Plugin for CudaText.
Gives intelligence commands for JavaScript, using Tern engine, http://ternjs.net/

1) Auto-completion (Ctrl+Space)
2) Go-to-definition (command item in editor context menu)
3) Show function/class call-tip (Ctrl+Shift+Space, info will show at the editor bottom)
4) Show function/class/var doc-string (comment above function definition, info will show in the Output panel)

======================================
First, you must install Node.js engine, then install Tern like this:
  [sudo] npm install tern -g

Lexer name "JavaScript" is set in the file install.inf, you may append names of other JS-based lexers, after comma.

======================================
For complex code with some files, with "require" JS commands, you must make a project!
To create a project, install "Project Manager" CudaText plugin and open its panel, then create a project, add to project your JS files (tested with js files in one folder). Save resulting project file (name.cuda-proj) to the same folder as JS files. This project must be opened (in Proj Manager) before calling auto-completion/ go-to-definition, else Tern will not find other JS files (so no completions for functions from other files). Plugin makes simple .tern-project file to help Tern.


Authors:
- https://github.com/pohmelie/
- Alexey T. (CudaText)
    
License: MIT
