" Vim syntax file
" Language:     Cubicle
" Filenames:    *.cub

" For version 5.x: Clear all syntax items
" For version 6.x: Quit when a syntax file was already loaded
if version < 600
  syntax clear
elseif exists("b:current_syntax") && b:current_syntax == "cubicle"
  finish
endif

" Cubicle is case sensitive.
syn case match

" Script headers highlighted like comments
syn match    cubicleComment   "^#!.*" contains=@Spell


" Errors
syn match    cubicleBraceErr   "}"
syn match    cubicleBrackErr   "\]"
syn match    cubicleParenErr   ")"

syn match    cubicleCommentErr "\*)"

" Some convenient clusters
syn cluster  cubicleContained contains=cubicleTodo


" Enclosing delimiters
syn region   cubicleEncl transparent matchgroup=cubicleKeyword start="(" matchgroup=cubicleKeyword end=")" contains=ALLBUT,@cubicleContained,cubicleParenErr
syn region   cubicleEncl transparent matchgroup=cubicleKeyword start="{" matchgroup=cubicleKeyword end="}"  contains=ALLBUT,@cubicleContained,cubicleBraceErr
syn region   cubicleEncl transparent matchgroup=cubicleKeyword start="\[" matchgroup=cubicleKeyword end="\]" contains=ALLBUT,@cubicleContained,cubicleBrackErr


" Comments
syn region   cubicleComment start="(\*" end="\*)" contains=@Spell,cubicleComment,cubicleTodo
syn keyword  cubicleTodo contained TODO FIXME XXX NOTE

syn keyword  cubicleKeyword  type array var const
syn keyword  cubicleKeyword  init unsafe
syn keyword  cubicleKeyword  invariant number_procs
syn keyword  cubicleKeyword  transition requires
syn keyword  cubicleKeyword  forall_other case


syn keyword  cubicleBoolean  True False

syn keyword  cubicleType     bool real int proc

syn match    cubicleLCIdentifier /\<\l\(\w\|@\|\.\)*\>/

syn match    cubicleOperator    ":="
syn match    cubicleOperator     "&&"
syn match    cubicleOperator     "||"
syn match    cubicleOperator     "<"
syn match    cubicleOperator     ">"
syn match    cubicleOperator      "="

syn match    cubicleSymbol       "\<_\>"
syn match    cubicleSymbol       "?"

syn match    cubicleStateVariable  "\u\(\w\|@\|\.\)*"

syn match    cubicleKeyChar    "|"
syn match    cubicleKeyChar      ";"
syn match    cubicleKeyChar      ":"
syn match    cubicleKeyChar      "\."
syn match    cubicleKeyChar      "@"

syn match    cubicleNumber        "\<-\=\d\(_\|\d\)*[l|L|n]\?\>"
syn match    cubicleFloat         "\<-\=\d\(_\|\d\)*\.\?\(_\|\d\)*\([eE][-+]\=\d\(_\|\d\)*\)\=\>"


" Define the default highlighting.
" For version 5.7 and earlier: only when not done already
" For version 5.8 and later: only when an item doesn't have highlighting yet
if version >= 508 || !exists("did_cubicle_syntax_inits")
   if version < 508
      let did_cubicle_syntax_inits = 1
      command -nargs=+ HiLink hi link <args>
   else
      command -nargs=+ HiLink hi def link <args>
   endif

   HiLink cubicleBraceErr	   Error
   HiLink cubicleBrackErr	   Error
   HiLink cubicleParenErr	   Error

   HiLink cubicleCommentErr   Error

   HiLink cubicleComment	   Comment

   HiLink cubicleKeyword	   Statement
   HiLink cubicleKeyChar	   Delimiter
   HiLink cubicleSymbol	   SpecialChar
   HiLink cubicleOperator   Operator

   HiLink cubicleStateVariable Identifier

   HiLink cubicleBoolean	   Boolean
   HiLink cubicleNumber	   Number
   HiLink cubicleFloat	   Float

   HiLink cubicleType	   Type

   HiLink cubicleTodo	   Todo

   HiLink cubicleEncl	   Statement

   delcommand HiLink
endif

let b:current_syntax = "cubicle"

" vim: ts=8
