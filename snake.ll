; Generated from independently checked xMLF.
source_filename = "emlf"

declare ptr @mlf_env_new(i64)
declare void @mlf_env_set(ptr, i64, ptr)
declare ptr @mlf_env_get(ptr, i64)
declare ptr @mlf_thunk(ptr, ptr)
declare ptr @mlf_closure(ptr, ptr)
declare ptr @mlf_application(ptr, ptr)
declare ptr @mlf_hole()
declare void @mlf_fill(ptr, ptr)
declare ptr @mlf_integer(ptr)
declare ptr @mlf_boolean(i64)
declare ptr @mlf_string(ptr, i64)
declare ptr @mlf_primitive(i64)
declare ptr @mlf_constructor(i64, i64)
declare i64 @mlf_tag(ptr)
declare ptr @mlf_field(ptr, i64)
declare void @mlf_match_failure() noreturn
declare i32 @mlf_run(ptr, i64)

@mlf.bytes.63 = private unnamed_addr constant [3 x i8] c"\31\32\00", align 1
@mlf.bytes.65 = private unnamed_addr constant [2 x i8] c"\38\00", align 1
@mlf.bytes.197 = private unnamed_addr constant [2 x i8] c"\31\00", align 1
@mlf.bytes.205 = private unnamed_addr constant [2 x i8] c"\31\00", align 1
@mlf.bytes.212 = private unnamed_addr constant [2 x i8] c"\31\00", align 1
@mlf.bytes.220 = private unnamed_addr constant [2 x i8] c"\31\00", align 1
@mlf.bytes.275 = private unnamed_addr constant [2 x i8] c"\30\00", align 1
@mlf.bytes.281 = private unnamed_addr constant [2 x i8] c"\30\00", align 1
@mlf.bytes.339 = private unnamed_addr constant [2 x i8] c"\30\00", align 1
@mlf.bytes.344 = private unnamed_addr constant [2 x i8] c"\31\00", align 1
@mlf.bytes.364 = private unnamed_addr constant [2 x i8] c"\31\00", align 1
@mlf.bytes.385 = private unnamed_addr constant [2 x i8] c"\30\00", align 1
@mlf.bytes.388 = private unnamed_addr constant [2 x i8] c"\30\00", align 1
@mlf.bytes.459 = private unnamed_addr constant [5 x i8] c"\77\61\6c\6c\00", align 1
@mlf.bytes.469 = private unnamed_addr constant [5 x i8] c"\62\6f\64\79\00", align 1
@mlf.bytes.485 = private unnamed_addr constant [2 x i8] c"\31\00", align 1
@mlf.bytes.528 = private unnamed_addr constant [2 x i8] c"\71\00", align 1
@mlf.bytes.537 = private unnamed_addr constant [2 x i8] c"\77\00", align 1
@mlf.bytes.548 = private unnamed_addr constant [2 x i8] c"\73\00", align 1
@mlf.bytes.559 = private unnamed_addr constant [2 x i8] c"\61\00", align 1
@mlf.bytes.570 = private unnamed_addr constant [2 x i8] c"\64\00", align 1
@mlf.bytes.581 = private unnamed_addr constant [1 x i8] c"\00", align 1
@mlf.bytes.618 = private unnamed_addr constant [2 x i8] c"\40\00", align 1
@mlf.bytes.625 = private unnamed_addr constant [2 x i8] c"\6f\00", align 1
@mlf.bytes.632 = private unnamed_addr constant [2 x i8] c"\2a\00", align 1
@mlf.bytes.635 = private unnamed_addr constant [2 x i8] c"\2e\00", align 1
@mlf.bytes.679 = private unnamed_addr constant [3 x i8] c"\7c\0a\00", align 1
@mlf.bytes.691 = private unnamed_addr constant [2 x i8] c"\31\00", align 1
@mlf.bytes.704 = private unnamed_addr constant [2 x i8] c"\7c\00", align 1
@mlf.bytes.707 = private unnamed_addr constant [2 x i8] c"\30\00", align 1
@mlf.bytes.735 = private unnamed_addr constant [1 x i8] c"\00", align 1
@mlf.bytes.745 = private unnamed_addr constant [2 x i8] c"\31\00", align 1
@mlf.bytes.766 = private unnamed_addr constant [3 x i8] c"\75\70\00", align 1
@mlf.bytes.768 = private unnamed_addr constant [5 x i8] c"\64\6f\77\6e\00", align 1
@mlf.bytes.770 = private unnamed_addr constant [5 x i8] c"\6c\65\66\74\00", align 1
@mlf.bytes.772 = private unnamed_addr constant [6 x i8] c"\72\69\67\68\74\00", align 1
@mlf.bytes.795 = private unnamed_addr constant [9 x i8] c"\0a\53\63\6f\72\65\3a\20\00", align 1
@mlf.bytes.803 = private unnamed_addr constant [14 x i8] c"\20\20\44\69\72\65\63\74\69\6f\6e\3a\20\00", align 1
@mlf.bytes.819 = private unnamed_addr constant [15 x i8] c"\2b\2d\2d\2d\2d\2d\2d\2d\2d\2d\2d\2d\2d\2b\00", align 1
@mlf.bytes.831 = private unnamed_addr constant [2 x i8] c"\30\00", align 1
@mlf.bytes.838 = private unnamed_addr constant [15 x i8] c"\2b\2d\2d\2d\2d\2d\2d\2d\2d\2d\2d\2d\2d\2b\00", align 1
@mlf.bytes.879 = private unnamed_addr constant [27 x i8] c"\4d\6f\76\65\20\5b\77\2f\61\2f\73\2f\64\2c\20\45\6e\74\65\72\2c\20\71\5d\3a\20\00", align 1
@mlf.bytes.924 = private unnamed_addr constant [16 x i8] c"\47\61\6d\65\20\6f\76\65\72\3a\20\68\69\74\20\00", align 1
@mlf.bytes.930 = private unnamed_addr constant [10 x i8] c"\2e\20\53\63\6f\72\65\3a\20\00", align 1
@mlf.bytes.942 = private unnamed_addr constant [30 x i8] c"\59\6f\75\20\66\69\6c\6c\65\64\20\74\68\65\20\62\6f\61\72\64\21\20\53\63\6f\72\65\3a\20\00", align 1
@mlf.bytes.960 = private unnamed_addr constant [17 x i8] c"\47\6f\6f\64\62\79\65\2e\20\53\63\6f\72\65\3a\20\00", align 1
@mlf.bytes.969 = private unnamed_addr constant [43 x i8] c"\55\73\65\20\77\2c\20\61\2c\20\73\2c\20\64\2c\20\45\6e\74\65\72\2c\20\6f\72\20\71\2e\20\4e\6f\20\6d\6f\76\65\20\6d\61\64\65\2e\00", align 1
@mlf.bytes.1001 = private unnamed_addr constant [2 x i8] c"\34\00", align 1
@mlf.bytes.1004 = private unnamed_addr constant [2 x i8] c"\33\00", align 1
@mlf.bytes.1010 = private unnamed_addr constant [2 x i8] c"\33\00", align 1
@mlf.bytes.1013 = private unnamed_addr constant [2 x i8] c"\33\00", align 1
@mlf.bytes.1019 = private unnamed_addr constant [2 x i8] c"\32\00", align 1
@mlf.bytes.1022 = private unnamed_addr constant [2 x i8] c"\33\00", align 1
@mlf.bytes.1034 = private unnamed_addr constant [2 x i8] c"\36\00", align 1
@mlf.bytes.1037 = private unnamed_addr constant [2 x i8] c"\33\00", align 1
@mlf.bytes.1041 = private unnamed_addr constant [2 x i8] c"\30\00", align 1
@mlf.bytes.1046 = private unnamed_addr constant [53 x i8] c"\53\6e\61\6b\65\3a\20\40\20\68\65\61\64\2c\20\6f\20\62\6f\64\79\2c\20\2a\20\66\6f\6f\64\2e\20\54\68\65\20\62\6f\61\72\64\20\69\73\20\31\32\20\62\79\20\38\2e\00", align 1
@mlf.bytes.1057 = private unnamed_addr constant [73 x i8] c"\57\41\53\44\20\2b\20\45\6e\74\65\72\20\6d\6f\76\65\73\3b\20\45\6e\74\65\72\20\63\6f\6e\74\69\6e\75\65\73\3b\20\71\20\71\75\69\74\73\2e\20\52\65\76\65\72\73\65\20\74\75\72\6e\73\20\61\72\65\20\69\67\6e\6f\72\65\64\2e\00", align 1
@mlf.bytes.1068 = private unnamed_addr constant [78 x i8] c"\45\61\74\20\66\6f\6f\64\20\74\6f\20\67\72\6f\77\2e\20\41\76\6f\69\64\20\77\61\6c\6c\73\20\61\6e\64\20\79\6f\75\72\20\62\6f\64\79\2e\20\46\6f\6f\64\20\75\73\65\73\20\74\68\65\20\66\69\72\73\74\20\66\72\65\65\20\73\71\75\61\72\65\2e\00", align 1
define private ptr @mlf.code.4(ptr %env, ptr %arg) {
entry:
  ret ptr %arg
}

define private ptr @mlf.code.7(ptr %env, ptr %arg) {
entry:
  ret ptr %arg
}

define private ptr @mlf.code.6(ptr %env, ptr %arg) {
entry:
  %v8 = call ptr @mlf_closure(ptr @mlf.code.7, ptr null)
  %v9 = call ptr @mlf_application(ptr %v8, ptr %arg)
  %v10 = call i64 @mlf_tag(ptr %v9)
  switch i64 %v10, label %case.missing.12 [
    i64 20, label %case.11
  ]
case.11:
  %v13 = call ptr @mlf_field(ptr %v9, i64 0)
  ret ptr %v13
case.missing.12:
  call void @mlf_match_failure()
  unreachable
}

define private ptr @mlf.code.16(ptr %env, ptr %arg) {
entry:
  ret ptr %arg
}

define private ptr @mlf.code.19(ptr %env, ptr %arg) {
entry:
  ret ptr %arg
}

define private ptr @mlf.code.18(ptr %env, ptr %arg) {
entry:
  %v20 = call ptr @mlf_closure(ptr @mlf.code.19, ptr null)
  %v21 = call ptr @mlf_application(ptr %v20, ptr %arg)
  %v22 = call i64 @mlf_tag(ptr %v21)
  switch i64 %v22, label %case.missing.24 [
    i64 20, label %case.23
  ]
case.23:
  %v25 = call ptr @mlf_field(ptr %v21, i64 1)
  ret ptr %v25
case.missing.24:
  call void @mlf_match_failure()
  unreachable
}

define private ptr @mlf.code.28(ptr %env, ptr %arg) {
entry:
  ret ptr %arg
}

define private ptr @mlf.code.31(ptr %env, ptr %arg) {
entry:
  ret ptr %arg
}

define private ptr @mlf.code.36(ptr %env, ptr %arg) {
entry:
  ret ptr %arg
}

define private ptr @mlf.code.42(ptr %env, ptr %arg) {
entry:
  ret ptr %arg
}

define private ptr @mlf.code.45(ptr %env, ptr %arg) {
entry:
  ret ptr %arg
}

define private ptr @mlf.code.48(ptr %env, ptr %arg) {
entry:
  %v49 = call ptr @mlf_env_get(ptr %env, i64 0)
  %v50 = call i64 @mlf_tag(ptr %arg)
  switch i64 %v50, label %case.missing.52 [
    i64 19, label %case.51
  ]
case.51:
  %v53 = call ptr @mlf_field(ptr %arg, i64 0)
  %v54 = call ptr @mlf_application(ptr %v53, ptr %arg)
  %v55 = call ptr @mlf_application(ptr %v49, ptr %v54)
  ret ptr %v55
case.missing.52:
  call void @mlf_match_failure()
  unreachable
}

define private ptr @mlf.code.44(ptr %env, ptr %arg) {
entry:
  %v46 = call ptr @mlf_closure(ptr @mlf.code.45, ptr null)
  %v47 = call ptr @mlf_application(ptr %v46, ptr %arg)
  %v56 = call ptr @mlf_env_new(i64 1)
  call void @mlf_env_set(ptr %v56, i64 0, ptr %v47)
  %v57 = call ptr @mlf_closure(ptr @mlf.code.48, ptr %v56)
  %v58 = call ptr @mlf_constructor(i64 19, i64 1)
  %v59 = call ptr @mlf_application(ptr %v58, ptr %v57)
  %v60 = call ptr @mlf_application(ptr %v57, ptr %v59)
  ret ptr %v60
}

define private ptr @mlf.code.68(ptr %env, ptr %arg) {
entry:
  %v69 = call ptr @mlf_env_get(ptr %env, i64 0)
  %v70 = call ptr @mlf_primitive(i64 13)
  %v71 = call ptr @mlf_application(ptr %v70, ptr %v69)
  %v72 = call ptr @mlf_application(ptr %v71, ptr %arg)
  %v73 = call ptr @mlf_boolean(i64 0)
  %v74 = call ptr @mlf_application(ptr %v72, ptr %v73)
  ret ptr %v74
}

define private ptr @mlf.code.67(ptr %env, ptr %arg) {
entry:
  %v75 = call ptr @mlf_env_new(i64 1)
  call void @mlf_env_set(ptr %v75, i64 0, ptr %arg)
  %v76 = call ptr @mlf_closure(ptr @mlf.code.68, ptr %v75)
  ret ptr %v76
}

define private ptr @mlf.code.79(ptr %env, ptr %arg) {
entry:
  %v80 = call ptr @mlf_env_get(ptr %env, i64 0)
  %v81 = call ptr @mlf_primitive(i64 13)
  %v82 = call ptr @mlf_application(ptr %v81, ptr %v80)
  %v83 = call ptr @mlf_boolean(i64 1)
  %v84 = call ptr @mlf_application(ptr %v82, ptr %v83)
  %v85 = call ptr @mlf_application(ptr %v84, ptr %arg)
  ret ptr %v85
}

define private ptr @mlf.code.78(ptr %env, ptr %arg) {
entry:
  %v86 = call ptr @mlf_env_new(i64 1)
  call void @mlf_env_set(ptr %v86, i64 0, ptr %arg)
  %v87 = call ptr @mlf_closure(ptr @mlf.code.79, ptr %v86)
  ret ptr %v87
}

define private ptr @mlf.code.91(ptr %env, ptr %arg) {
entry:
  %v92 = call ptr @mlf_env_get(ptr %env, i64 0)
  %v93 = call ptr @mlf_env_get(ptr %env, i64 1)
  %v94 = call i64 @mlf_tag(ptr %v93)
  switch i64 %v94, label %case.missing.96 [
    i64 5, label %case.95
  ]
case.95:
  %v97 = call ptr @mlf_field(ptr %v93, i64 0)
  %v98 = call ptr @mlf_field(ptr %v93, i64 1)
  %v99 = call i64 @mlf_tag(ptr %arg)
  switch i64 %v99, label %case.missing.101 [
    i64 5, label %case.100
  ]
case.100:
  %v102 = call ptr @mlf_field(ptr %arg, i64 0)
  %v103 = call ptr @mlf_field(ptr %arg, i64 1)
  %v104 = call ptr @mlf_primitive(i64 10)
  %v105 = call ptr @mlf_application(ptr %v104, ptr %v97)
  %v106 = call ptr @mlf_application(ptr %v105, ptr %v102)
  %v107 = call ptr @mlf_application(ptr %v92, ptr %v106)
  %v108 = call ptr @mlf_primitive(i64 10)
  %v109 = call ptr @mlf_application(ptr %v108, ptr %v98)
  %v110 = call ptr @mlf_application(ptr %v109, ptr %v103)
  %v111 = call ptr @mlf_application(ptr %v107, ptr %v110)
  ret ptr %v111
case.missing.101:
  call void @mlf_match_failure()
  unreachable
case.missing.96:
  call void @mlf_match_failure()
  unreachable
}

define private ptr @mlf.code.89(ptr %env, ptr %arg) {
entry:
  %v90 = call ptr @mlf_env_get(ptr %env, i64 0)
  %v112 = call ptr @mlf_env_new(i64 2)
  call void @mlf_env_set(ptr %v112, i64 0, ptr %v90)
  call void @mlf_env_set(ptr %v112, i64 1, ptr %arg)
  %v113 = call ptr @mlf_closure(ptr @mlf.code.91, ptr %v112)
  ret ptr %v113
}

define private ptr @mlf.code.116(ptr %env, ptr %arg) {
entry:
  ret ptr %arg
}

define private ptr @mlf.code.125(ptr %env, ptr %arg) {
entry:
  %v126 = call ptr @mlf_env_get(ptr %env, i64 0)
  %v127 = call ptr @mlf_env_get(ptr %env, i64 1)
  %v128 = call ptr @mlf_env_get(ptr %env, i64 2)
  %v129 = call ptr @mlf_env_get(ptr %env, i64 3)
  %v130 = call i64 @mlf_tag(ptr %arg)
  switch i64 %v130, label %case.missing.133 [
    i64 1, label %case.131
    i64 2, label %case.132
  ]
case.131:
  %v134 = call ptr @mlf_boolean(i64 0)
  ret ptr %v134
case.132:
  %v135 = call ptr @mlf_field(ptr %arg, i64 0)
  %v136 = call ptr @mlf_field(ptr %arg, i64 1)
  %v137 = call ptr @mlf_application(ptr %v127, ptr %v129)
  %v138 = call ptr @mlf_application(ptr %v137, ptr %v135)
  %v139 = call ptr @mlf_application(ptr %v126, ptr %v138)
  %v140 = call ptr @mlf_application(ptr %v128, ptr %v129)
  %v141 = call ptr @mlf_application(ptr %v140, ptr %v136)
  %v142 = call ptr @mlf_application(ptr %v139, ptr %v141)
  ret ptr %v142
case.missing.133:
  call void @mlf_match_failure()
  unreachable
}

define private ptr @mlf.code.121(ptr %env, ptr %arg) {
entry:
  %v122 = call ptr @mlf_env_get(ptr %env, i64 0)
  %v123 = call ptr @mlf_env_get(ptr %env, i64 1)
  %v124 = call ptr @mlf_env_get(ptr %env, i64 2)
  %v143 = call ptr @mlf_env_new(i64 4)
  call void @mlf_env_set(ptr %v143, i64 0, ptr %v122)
  call void @mlf_env_set(ptr %v143, i64 1, ptr %v123)
  call void @mlf_env_set(ptr %v143, i64 2, ptr %v124)
  call void @mlf_env_set(ptr %v143, i64 3, ptr %arg)
  %v144 = call ptr @mlf_closure(ptr @mlf.code.125, ptr %v143)
  ret ptr %v144
}

define private ptr @mlf.code.118(ptr %env, ptr %arg) {
entry:
  %v119 = call ptr @mlf_env_get(ptr %env, i64 0)
  %v120 = call ptr @mlf_env_get(ptr %env, i64 1)
  %v145 = call ptr @mlf_env_new(i64 3)
  call void @mlf_env_set(ptr %v145, i64 0, ptr %v119)
  call void @mlf_env_set(ptr %v145, i64 1, ptr %v120)
  call void @mlf_env_set(ptr %v145, i64 2, ptr %arg)
  %v146 = call ptr @mlf_closure(ptr @mlf.code.121, ptr %v145)
  ret ptr %v146
}

define private ptr @mlf.code.151(ptr %env, ptr %arg) {
entry:
  ret ptr %arg
}

define private ptr @mlf.code.154(ptr %env, ptr %arg) {
entry:
  %v155 = call ptr @mlf_env_get(ptr %env, i64 0)
  %v156 = call i64 @mlf_tag(ptr %arg)
  switch i64 %v156, label %case.missing.159 [
    i64 1, label %case.157
    i64 2, label %case.158
  ]
case.157:
  %v160 = call ptr @mlf_constructor(i64 1, i64 0)
  ret ptr %v160
case.158:
  %v161 = call ptr @mlf_field(ptr %arg, i64 0)
  %v162 = call ptr @mlf_field(ptr %arg, i64 1)
  %v163 = call i64 @mlf_tag(ptr %v162)
  switch i64 %v163, label %case.missing.166 [
    i64 1, label %case.164
    i64 2, label %case.165
  ]
case.164:
  %v167 = call ptr @mlf_constructor(i64 1, i64 0)
  ret ptr %v167
case.165:
  %v168 = call ptr @mlf_field(ptr %v162, i64 0)
  %v169 = call ptr @mlf_field(ptr %v162, i64 1)
  %v170 = call ptr @mlf_constructor(i64 2, i64 2)
  %v171 = call ptr @mlf_application(ptr %v170, ptr %v161)
  %v172 = call ptr @mlf_application(ptr %v155, ptr %v162)
  %v173 = call ptr @mlf_application(ptr %v171, ptr %v172)
  ret ptr %v173
case.missing.166:
  call void @mlf_match_failure()
  unreachable
case.missing.159:
  call void @mlf_match_failure()
  unreachable
}

define private ptr @mlf.code.153(ptr %env, ptr %arg) {
entry:
  %v174 = call ptr @mlf_env_new(i64 1)
  call void @mlf_env_set(ptr %v174, i64 0, ptr %arg)
  %v175 = call ptr @mlf_closure(ptr @mlf.code.154, ptr %v174)
  ret ptr %v175
}

define private ptr @mlf.code.180(ptr %env, ptr %arg) {
entry:
  %v181 = call ptr @mlf_env_get(ptr %env, i64 0)
  %v182 = call i64 @mlf_tag(ptr %arg)
  switch i64 %v182, label %case.missing.184 [
    i64 5, label %case.183
  ]
case.183:
  %v185 = call ptr @mlf_field(ptr %arg, i64 0)
  %v186 = call ptr @mlf_field(ptr %arg, i64 1)
  %v187 = call i64 @mlf_tag(ptr %v181)
  switch i64 %v187, label %case.missing.192 [
    i64 6, label %case.188
    i64 7, label %case.189
    i64 8, label %case.190
    i64 9, label %case.191
  ]
case.188:
  %v193 = call ptr @mlf_constructor(i64 5, i64 2)
  %v194 = call ptr @mlf_application(ptr %v193, ptr %v185)
  %v195 = call ptr @mlf_primitive(i64 9)
  %v196 = call ptr @mlf_application(ptr %v195, ptr %v186)
  %v198 = call ptr @mlf_integer(ptr @mlf.bytes.197)
  %v199 = call ptr @mlf_application(ptr %v196, ptr %v198)
  %v200 = call ptr @mlf_application(ptr %v194, ptr %v199)
  ret ptr %v200
case.189:
  %v201 = call ptr @mlf_constructor(i64 5, i64 2)
  %v202 = call ptr @mlf_application(ptr %v201, ptr %v185)
  %v203 = call ptr @mlf_primitive(i64 8)
  %v204 = call ptr @mlf_application(ptr %v203, ptr %v186)
  %v206 = call ptr @mlf_integer(ptr @mlf.bytes.205)
  %v207 = call ptr @mlf_application(ptr %v204, ptr %v206)
  %v208 = call ptr @mlf_application(ptr %v202, ptr %v207)
  ret ptr %v208
case.190:
  %v209 = call ptr @mlf_constructor(i64 5, i64 2)
  %v210 = call ptr @mlf_primitive(i64 9)
  %v211 = call ptr @mlf_application(ptr %v210, ptr %v185)
  %v213 = call ptr @mlf_integer(ptr @mlf.bytes.212)
  %v214 = call ptr @mlf_application(ptr %v211, ptr %v213)
  %v215 = call ptr @mlf_application(ptr %v209, ptr %v214)
  %v216 = call ptr @mlf_application(ptr %v215, ptr %v186)
  ret ptr %v216
case.191:
  %v217 = call ptr @mlf_constructor(i64 5, i64 2)
  %v218 = call ptr @mlf_primitive(i64 8)
  %v219 = call ptr @mlf_application(ptr %v218, ptr %v185)
  %v221 = call ptr @mlf_integer(ptr @mlf.bytes.220)
  %v222 = call ptr @mlf_application(ptr %v219, ptr %v221)
  %v223 = call ptr @mlf_application(ptr %v217, ptr %v222)
  %v224 = call ptr @mlf_application(ptr %v223, ptr %v186)
  ret ptr %v224
case.missing.192:
  call void @mlf_match_failure()
  unreachable
case.missing.184:
  call void @mlf_match_failure()
  unreachable
}

define private ptr @mlf.code.179(ptr %env, ptr %arg) {
entry:
  %v225 = call ptr @mlf_env_new(i64 1)
  call void @mlf_env_set(ptr %v225, i64 0, ptr %arg)
  %v226 = call ptr @mlf_closure(ptr @mlf.code.180, ptr %v225)
  ret ptr %v226
}

define private ptr @mlf.code.229(ptr %env, ptr %arg) {
entry:
  %v230 = call ptr @mlf_env_get(ptr %env, i64 0)
  %v231 = call i64 @mlf_tag(ptr %v230)
  switch i64 %v231, label %case.missing.236 [
    i64 6, label %case.232
    i64 7, label %case.233
    i64 8, label %case.234
    i64 9, label %case.235
  ]
case.232:
  %v237 = call i64 @mlf_tag(ptr %arg)
  switch i64 %v237, label %case.239 [
    i64 7, label %case.238
  ]
case.238:
  %v241 = call ptr @mlf_boolean(i64 1)
  ret ptr %v241
case.239:
  %v242 = call ptr @mlf_boolean(i64 0)
  ret ptr %v242
case.233:
  %v243 = call i64 @mlf_tag(ptr %arg)
  switch i64 %v243, label %case.245 [
    i64 6, label %case.244
  ]
case.244:
  %v247 = call ptr @mlf_boolean(i64 1)
  ret ptr %v247
case.245:
  %v248 = call ptr @mlf_boolean(i64 0)
  ret ptr %v248
case.234:
  %v249 = call i64 @mlf_tag(ptr %arg)
  switch i64 %v249, label %case.251 [
    i64 9, label %case.250
  ]
case.250:
  %v253 = call ptr @mlf_boolean(i64 1)
  ret ptr %v253
case.251:
  %v254 = call ptr @mlf_boolean(i64 0)
  ret ptr %v254
case.235:
  %v255 = call i64 @mlf_tag(ptr %arg)
  switch i64 %v255, label %case.257 [
    i64 8, label %case.256
  ]
case.256:
  %v259 = call ptr @mlf_boolean(i64 1)
  ret ptr %v259
case.257:
  %v260 = call ptr @mlf_boolean(i64 0)
  ret ptr %v260
case.missing.236:
  call void @mlf_match_failure()
  unreachable
}

define private ptr @mlf.code.228(ptr %env, ptr %arg) {
entry:
  %v261 = call ptr @mlf_env_new(i64 1)
  call void @mlf_env_set(ptr %v261, i64 0, ptr %arg)
  %v262 = call ptr @mlf_closure(ptr @mlf.code.229, ptr %v261)
  ret ptr %v262
}

define private ptr @mlf.code.264(ptr %env, ptr %arg) {
entry:
  %v265 = call ptr @mlf_env_get(ptr %env, i64 0)
  %v266 = call ptr @mlf_env_get(ptr %env, i64 1)
  %v267 = call ptr @mlf_env_get(ptr %env, i64 2)
  %v268 = call i64 @mlf_tag(ptr %arg)
  switch i64 %v268, label %case.missing.270 [
    i64 5, label %case.269
  ]
case.269:
  %v271 = call ptr @mlf_field(ptr %arg, i64 0)
  %v272 = call ptr @mlf_field(ptr %arg, i64 1)
  %v273 = call ptr @mlf_primitive(i64 11)
  %v274 = call ptr @mlf_application(ptr %v273, ptr %v271)
  %v276 = call ptr @mlf_integer(ptr @mlf.bytes.275)
  %v277 = call ptr @mlf_application(ptr %v274, ptr %v276)
  %v278 = call ptr @mlf_application(ptr %v267, ptr %v277)
  %v279 = call ptr @mlf_primitive(i64 11)
  %v280 = call ptr @mlf_application(ptr %v279, ptr %v272)
  %v282 = call ptr @mlf_integer(ptr @mlf.bytes.281)
  %v283 = call ptr @mlf_application(ptr %v280, ptr %v282)
  %v284 = call ptr @mlf_application(ptr %v267, ptr %v283)
  %v285 = call ptr @mlf_primitive(i64 10)
  %v286 = call ptr @mlf_application(ptr %v285, ptr %v271)
  %v287 = call ptr @mlf_application(ptr %v286, ptr %v265)
  %v288 = call ptr @mlf_application(ptr %v267, ptr %v287)
  %v289 = call ptr @mlf_primitive(i64 10)
  %v290 = call ptr @mlf_application(ptr %v289, ptr %v272)
  %v291 = call ptr @mlf_application(ptr %v290, ptr %v266)
  %v292 = call ptr @mlf_application(ptr %v288, ptr %v291)
  %v293 = call ptr @mlf_application(ptr %v284, ptr %v292)
  %v294 = call ptr @mlf_application(ptr %v278, ptr %v293)
  ret ptr %v294
case.missing.270:
  call void @mlf_match_failure()
  unreachable
}

define private ptr @mlf.code.297(ptr %env, ptr %arg) {
entry:
  ret ptr %arg
}

define private ptr @mlf.code.304(ptr %env, ptr %arg) {
entry:
  ret ptr %arg
}

define private ptr @mlf.code.307(ptr %env, ptr %arg) {
entry:
  ret ptr %arg
}

define private ptr @mlf.code.349(ptr %env, ptr %arg) {
entry:
  %v350 = call ptr @mlf_env_get(ptr %env, i64 0)
  %v351 = call ptr @mlf_env_get(ptr %env, i64 1)
  %v352 = call ptr @mlf_env_get(ptr %env, i64 2)
  %v353 = call ptr @mlf_env_get(ptr %env, i64 3)
  %v354 = call ptr @mlf_env_get(ptr %env, i64 4)
  %v355 = call ptr @mlf_constructor(i64 5, i64 2)
  %v356 = call ptr @mlf_application(ptr %v355, ptr %v353)
  %v357 = call ptr @mlf_application(ptr %v356, ptr %v354)
  %v358 = call ptr @mlf_primitive(i64 13)
  %v359 = call ptr @mlf_application(ptr %v350, ptr %v357)
  %v360 = call ptr @mlf_application(ptr %v359, ptr %v351)
  %v361 = call ptr @mlf_application(ptr %v358, ptr %v360)
  %v362 = call ptr @mlf_primitive(i64 8)
  %v363 = call ptr @mlf_application(ptr %v362, ptr %v353)
  %v365 = call ptr @mlf_integer(ptr @mlf.bytes.364)
  %v366 = call ptr @mlf_application(ptr %v363, ptr %v365)
  %v367 = call ptr @mlf_application(ptr %v352, ptr %v366)
  %v368 = call ptr @mlf_application(ptr %v367, ptr %v354)
  %v369 = call ptr @mlf_application(ptr %v361, ptr %v368)
  %v370 = call ptr @mlf_constructor(i64 4, i64 1)
  %v371 = call ptr @mlf_application(ptr %v370, ptr %v357)
  %v372 = call ptr @mlf_application(ptr %v369, ptr %v371)
  ret ptr %v372
}

define private ptr @mlf.code.320(ptr %env, ptr %arg) {
entry:
  %v321 = call ptr @mlf_env_get(ptr %env, i64 0)
  %v322 = call ptr @mlf_env_get(ptr %env, i64 1)
  %v323 = call ptr @mlf_env_get(ptr %env, i64 2)
  %v324 = call ptr @mlf_env_get(ptr %env, i64 3)
  %v325 = call ptr @mlf_env_get(ptr %env, i64 4)
  %v326 = call ptr @mlf_env_get(ptr %env, i64 5)
  %v327 = call ptr @mlf_primitive(i64 13)
  %v328 = call ptr @mlf_primitive(i64 10)
  %v329 = call ptr @mlf_application(ptr %v328, ptr %arg)
  %v330 = call ptr @mlf_application(ptr %v329, ptr %v322)
  %v331 = call ptr @mlf_application(ptr %v327, ptr %v330)
  %v332 = call ptr @mlf_constructor(i64 3, i64 0)
  %v333 = call ptr @mlf_application(ptr %v331, ptr %v332)
  %v334 = call ptr @mlf_primitive(i64 13)
  %v335 = call ptr @mlf_primitive(i64 10)
  %v336 = call ptr @mlf_application(ptr %v335, ptr %v326)
  %v337 = call ptr @mlf_application(ptr %v336, ptr %v321)
  %v338 = call ptr @mlf_application(ptr %v334, ptr %v337)
  %v340 = call ptr @mlf_integer(ptr @mlf.bytes.339)
  %v341 = call ptr @mlf_application(ptr %v325, ptr %v340)
  %v342 = call ptr @mlf_primitive(i64 8)
  %v343 = call ptr @mlf_application(ptr %v342, ptr %arg)
  %v345 = call ptr @mlf_integer(ptr @mlf.bytes.344)
  %v346 = call ptr @mlf_application(ptr %v343, ptr %v345)
  %v347 = call ptr @mlf_application(ptr %v341, ptr %v346)
  %v348 = call ptr @mlf_application(ptr %v338, ptr %v347)
  %v373 = call ptr @mlf_env_new(i64 5)
  call void @mlf_env_set(ptr %v373, i64 0, ptr %v323)
  call void @mlf_env_set(ptr %v373, i64 1, ptr %v324)
  call void @mlf_env_set(ptr %v373, i64 2, ptr %v325)
  call void @mlf_env_set(ptr %v373, i64 3, ptr %v326)
  call void @mlf_env_set(ptr %v373, i64 4, ptr %arg)
  %v374 = call ptr @mlf_thunk(ptr @mlf.code.349, ptr %v373)
  %v375 = call ptr @mlf_application(ptr %v348, ptr %v374)
  %v376 = call ptr @mlf_application(ptr %v333, ptr %v375)
  ret ptr %v376
}

define private ptr @mlf.code.314(ptr %env, ptr %arg) {
entry:
  %v315 = call ptr @mlf_env_get(ptr %env, i64 0)
  %v316 = call ptr @mlf_env_get(ptr %env, i64 1)
  %v317 = call ptr @mlf_env_get(ptr %env, i64 2)
  %v318 = call ptr @mlf_env_get(ptr %env, i64 3)
  %v319 = call ptr @mlf_env_get(ptr %env, i64 4)
  %v377 = call ptr @mlf_env_new(i64 6)
  call void @mlf_env_set(ptr %v377, i64 0, ptr %v315)
  call void @mlf_env_set(ptr %v377, i64 1, ptr %v316)
  call void @mlf_env_set(ptr %v377, i64 2, ptr %v317)
  call void @mlf_env_set(ptr %v377, i64 3, ptr %v318)
  call void @mlf_env_set(ptr %v377, i64 4, ptr %v319)
  call void @mlf_env_set(ptr %v377, i64 5, ptr %arg)
  %v378 = call ptr @mlf_closure(ptr @mlf.code.320, ptr %v377)
  ret ptr %v378
}

define private ptr @mlf.code.309(ptr %env, ptr %arg) {
entry:
  %v310 = call ptr @mlf_env_get(ptr %env, i64 0)
  %v311 = call ptr @mlf_env_get(ptr %env, i64 1)
  %v312 = call ptr @mlf_env_get(ptr %env, i64 2)
  %v313 = call ptr @mlf_env_get(ptr %env, i64 3)
  %v379 = call ptr @mlf_env_new(i64 5)
  call void @mlf_env_set(ptr %v379, i64 0, ptr %v310)
  call void @mlf_env_set(ptr %v379, i64 1, ptr %v311)
  call void @mlf_env_set(ptr %v379, i64 2, ptr %v312)
  call void @mlf_env_set(ptr %v379, i64 3, ptr %v313)
  call void @mlf_env_set(ptr %v379, i64 4, ptr %arg)
  %v380 = call ptr @mlf_closure(ptr @mlf.code.314, ptr %v379)
  ret ptr %v380
}

define private ptr @mlf.code.299(ptr %env, ptr %arg) {
entry:
  %v300 = call ptr @mlf_env_get(ptr %env, i64 0)
  %v301 = call ptr @mlf_env_get(ptr %env, i64 1)
  %v302 = call ptr @mlf_env_get(ptr %env, i64 2)
  %v303 = call ptr @mlf_env_get(ptr %env, i64 3)
  %v305 = call ptr @mlf_closure(ptr @mlf.code.304, ptr null)
  %v306 = call ptr @mlf_application(ptr %v305, ptr %arg)
  %v308 = call ptr @mlf_closure(ptr @mlf.code.307, ptr null)
  %v381 = call ptr @mlf_env_new(i64 4)
  call void @mlf_env_set(ptr %v381, i64 0, ptr %v301)
  call void @mlf_env_set(ptr %v381, i64 1, ptr %v302)
  call void @mlf_env_set(ptr %v381, i64 2, ptr %v303)
  call void @mlf_env_set(ptr %v381, i64 3, ptr %v306)
  %v382 = call ptr @mlf_closure(ptr @mlf.code.309, ptr %v381)
  %v383 = call ptr @mlf_application(ptr %v300, ptr %v382)
  %v384 = call ptr @mlf_application(ptr %v308, ptr %v383)
  %v386 = call ptr @mlf_integer(ptr @mlf.bytes.385)
  %v387 = call ptr @mlf_application(ptr %v384, ptr %v386)
  %v389 = call ptr @mlf_integer(ptr @mlf.bytes.388)
  %v390 = call ptr @mlf_application(ptr %v387, ptr %v389)
  ret ptr %v390
}

define private ptr @mlf.code.394(ptr %env, ptr %arg) {
entry:
  ret ptr %arg
}

define private ptr @mlf.code.404(ptr %env, ptr %arg) {
entry:
  ret ptr %arg
}

define private ptr @mlf.code.416(ptr %env, ptr %arg) {
entry:
  ret ptr %arg
}

define private ptr @mlf.code.476(ptr %env, ptr %arg) {
entry:
  %v477 = call ptr @mlf_env_get(ptr %env, i64 0)
  %v478 = call ptr @mlf_env_get(ptr %env, i64 1)
  %v479 = call ptr @mlf_env_get(ptr %env, i64 2)
  %v480 = call ptr @mlf_env_get(ptr %env, i64 3)
  %v481 = call ptr @mlf_env_get(ptr %env, i64 4)
  %v482 = call ptr @mlf_env_get(ptr %env, i64 5)
  %v483 = call ptr @mlf_primitive(i64 8)
  %v484 = call ptr @mlf_application(ptr %v483, ptr %v478)
  %v486 = call ptr @mlf_integer(ptr @mlf.bytes.485)
  %v487 = call ptr @mlf_application(ptr %v484, ptr %v486)
  %v488 = call ptr @mlf_constructor(i64 2, i64 2)
  %v489 = call ptr @mlf_application(ptr %v488, ptr %v480)
  %v490 = call ptr @mlf_application(ptr %v489, ptr %v481)
  %v491 = call ptr @mlf_application(ptr %v477, ptr %v490)
  %v492 = call i64 @mlf_tag(ptr %v491)
  switch i64 %v492, label %case.missing.495 [
    i64 3, label %case.493
    i64 4, label %case.494
  ]
case.493:
  %v496 = call ptr @mlf_constructor(i64 18, i64 1)
  %v497 = call ptr @mlf_application(ptr %v496, ptr %v487)
  ret ptr %v497
case.494:
  %v498 = call ptr @mlf_field(ptr %v491, i64 0)
  %v499 = call ptr @mlf_constructor(i64 16, i64 1)
  %v500 = call ptr @mlf_constructor(i64 15, i64 4)
  %v501 = call ptr @mlf_application(ptr %v500, ptr %v482)
  %v502 = call ptr @mlf_application(ptr %v501, ptr %v479)
  %v503 = call ptr @mlf_application(ptr %v502, ptr %v498)
  %v504 = call ptr @mlf_application(ptr %v503, ptr %v487)
  %v505 = call ptr @mlf_application(ptr %v499, ptr %v504)
  ret ptr %v505
case.missing.495:
  call void @mlf_match_failure()
  unreachable
}

define private ptr @mlf.code.407(ptr %env, ptr %arg) {
entry:
  %v408 = call ptr @mlf_env_get(ptr %env, i64 0)
  %v409 = call ptr @mlf_env_get(ptr %env, i64 1)
  %v410 = call ptr @mlf_env_get(ptr %env, i64 2)
  %v411 = call ptr @mlf_env_get(ptr %env, i64 3)
  %v412 = call ptr @mlf_env_get(ptr %env, i64 4)
  %v413 = call ptr @mlf_env_get(ptr %env, i64 5)
  %v414 = call ptr @mlf_env_get(ptr %env, i64 6)
  %v415 = call ptr @mlf_env_get(ptr %env, i64 7)
  %v417 = call ptr @mlf_closure(ptr @mlf.code.416, ptr null)
  %v418 = call ptr @mlf_application(ptr %v417, ptr %arg)
  %v419 = call i64 @mlf_tag(ptr %v418)
  switch i64 %v419, label %case.missing.421 [
    i64 15, label %case.420
  ]
case.420:
  %v422 = call ptr @mlf_field(ptr %v418, i64 0)
  %v423 = call ptr @mlf_field(ptr %v418, i64 1)
  %v424 = call ptr @mlf_field(ptr %v418, i64 2)
  %v425 = call ptr @mlf_field(ptr %v418, i64 3)
  %v426 = call i64 @mlf_tag(ptr %v422)
  switch i64 %v426, label %case.missing.428 [
    i64 14, label %case.427
  ]
case.427:
  %v429 = call ptr @mlf_field(ptr %v422, i64 0)
  %v430 = call ptr @mlf_field(ptr %v422, i64 1)
  %v431 = call ptr @mlf_primitive(i64 13)
  %v432 = call ptr @mlf_application(ptr %v412, ptr %v423)
  %v433 = call ptr @mlf_application(ptr %v432, ptr %v415)
  %v434 = call ptr @mlf_application(ptr %v431, ptr %v433)
  %v435 = call ptr @mlf_application(ptr %v434, ptr %v423)
  %v436 = call ptr @mlf_application(ptr %v435, ptr %v415)
  %v437 = call ptr @mlf_application(ptr %v411, ptr %v436)
  %v438 = call ptr @mlf_application(ptr %v437, ptr %v429)
  %v439 = call ptr @mlf_application(ptr %v408, ptr %v438)
  %v440 = call ptr @mlf_application(ptr %v439, ptr %v424)
  %v441 = call ptr @mlf_primitive(i64 13)
  %v442 = call ptr @mlf_application(ptr %v441, ptr %v440)
  %v443 = call ptr @mlf_constructor(i64 2, i64 2)
  %v444 = call ptr @mlf_application(ptr %v443, ptr %v429)
  %v445 = call ptr @mlf_application(ptr %v444, ptr %v430)
  %v446 = call ptr @mlf_application(ptr %v442, ptr %v445)
  %v447 = call ptr @mlf_constructor(i64 2, i64 2)
  %v448 = call ptr @mlf_application(ptr %v447, ptr %v429)
  %v449 = call ptr @mlf_application(ptr %v448, ptr %v430)
  %v450 = call ptr @mlf_application(ptr %v410, ptr %v449)
  %v451 = call ptr @mlf_application(ptr %v446, ptr %v450)
  %v452 = call ptr @mlf_constructor(i64 14, i64 2)
  %v453 = call ptr @mlf_application(ptr %v452, ptr %v438)
  %v454 = call ptr @mlf_application(ptr %v453, ptr %v451)
  %v455 = call ptr @mlf_primitive(i64 13)
  %v456 = call ptr @mlf_application(ptr %v413, ptr %v438)
  %v457 = call ptr @mlf_application(ptr %v455, ptr %v456)
  %v458 = call ptr @mlf_constructor(i64 17, i64 2)
  %v460 = call ptr @mlf_string(ptr @mlf.bytes.459, i64 4)
  %v461 = call ptr @mlf_application(ptr %v458, ptr %v460)
  %v462 = call ptr @mlf_application(ptr %v461, ptr %v425)
  %v463 = call ptr @mlf_application(ptr %v457, ptr %v462)
  %v464 = call ptr @mlf_primitive(i64 13)
  %v465 = call ptr @mlf_application(ptr %v409, ptr %v438)
  %v466 = call ptr @mlf_application(ptr %v465, ptr %v451)
  %v467 = call ptr @mlf_application(ptr %v464, ptr %v466)
  %v468 = call ptr @mlf_constructor(i64 17, i64 2)
  %v470 = call ptr @mlf_string(ptr @mlf.bytes.469, i64 4)
  %v471 = call ptr @mlf_application(ptr %v468, ptr %v470)
  %v472 = call ptr @mlf_application(ptr %v471, ptr %v425)
  %v473 = call ptr @mlf_application(ptr %v467, ptr %v472)
  %v474 = call ptr @mlf_primitive(i64 13)
  %v475 = call ptr @mlf_application(ptr %v474, ptr %v440)
  %v506 = call ptr @mlf_env_new(i64 6)
  call void @mlf_env_set(ptr %v506, i64 0, ptr %v414)
  call void @mlf_env_set(ptr %v506, i64 1, ptr %v425)
  call void @mlf_env_set(ptr %v506, i64 2, ptr %v436)
  call void @mlf_env_set(ptr %v506, i64 3, ptr %v438)
  call void @mlf_env_set(ptr %v506, i64 4, ptr %v451)
  call void @mlf_env_set(ptr %v506, i64 5, ptr %v454)
  %v507 = call ptr @mlf_thunk(ptr @mlf.code.476, ptr %v506)
  %v508 = call ptr @mlf_application(ptr %v475, ptr %v507)
  %v509 = call ptr @mlf_constructor(i64 16, i64 1)
  %v510 = call ptr @mlf_constructor(i64 15, i64 4)
  %v511 = call ptr @mlf_application(ptr %v510, ptr %v454)
  %v512 = call ptr @mlf_application(ptr %v511, ptr %v436)
  %v513 = call ptr @mlf_application(ptr %v512, ptr %v424)
  %v514 = call ptr @mlf_application(ptr %v513, ptr %v425)
  %v515 = call ptr @mlf_application(ptr %v509, ptr %v514)
  %v516 = call ptr @mlf_application(ptr %v508, ptr %v515)
  %v517 = call ptr @mlf_application(ptr %v473, ptr %v516)
  %v518 = call ptr @mlf_application(ptr %v463, ptr %v517)
  ret ptr %v518
case.missing.428:
  call void @mlf_match_failure()
  unreachable
case.missing.421:
  call void @mlf_match_failure()
  unreachable
}

define private ptr @mlf.code.396(ptr %env, ptr %arg) {
entry:
  %v397 = call ptr @mlf_env_get(ptr %env, i64 0)
  %v398 = call ptr @mlf_env_get(ptr %env, i64 1)
  %v399 = call ptr @mlf_env_get(ptr %env, i64 2)
  %v400 = call ptr @mlf_env_get(ptr %env, i64 3)
  %v401 = call ptr @mlf_env_get(ptr %env, i64 4)
  %v402 = call ptr @mlf_env_get(ptr %env, i64 5)
  %v403 = call ptr @mlf_env_get(ptr %env, i64 6)
  %v405 = call ptr @mlf_closure(ptr @mlf.code.404, ptr null)
  %v406 = call ptr @mlf_application(ptr %v405, ptr %arg)
  %v519 = call ptr @mlf_env_new(i64 8)
  call void @mlf_env_set(ptr %v519, i64 0, ptr %v397)
  call void @mlf_env_set(ptr %v519, i64 1, ptr %v398)
  call void @mlf_env_set(ptr %v519, i64 2, ptr %v399)
  call void @mlf_env_set(ptr %v519, i64 3, ptr %v400)
  call void @mlf_env_set(ptr %v519, i64 4, ptr %v401)
  call void @mlf_env_set(ptr %v519, i64 5, ptr %v402)
  call void @mlf_env_set(ptr %v519, i64 6, ptr %v403)
  call void @mlf_env_set(ptr %v519, i64 7, ptr %v406)
  %v520 = call ptr @mlf_closure(ptr @mlf.code.407, ptr %v519)
  ret ptr %v520
}

define private ptr @mlf.code.524(ptr %env, ptr %arg) {
entry:
  %v525 = call ptr @mlf_primitive(i64 13)
  %v526 = call ptr @mlf_primitive(i64 12)
  %v527 = call ptr @mlf_application(ptr %v526, ptr %arg)
  %v529 = call ptr @mlf_string(ptr @mlf.bytes.528, i64 1)
  %v530 = call ptr @mlf_application(ptr %v527, ptr %v529)
  %v531 = call ptr @mlf_application(ptr %v525, ptr %v530)
  %v532 = call ptr @mlf_constructor(i64 12, i64 0)
  %v533 = call ptr @mlf_application(ptr %v531, ptr %v532)
  %v534 = call ptr @mlf_primitive(i64 13)
  %v535 = call ptr @mlf_primitive(i64 12)
  %v536 = call ptr @mlf_application(ptr %v535, ptr %arg)
  %v538 = call ptr @mlf_string(ptr @mlf.bytes.537, i64 1)
  %v539 = call ptr @mlf_application(ptr %v536, ptr %v538)
  %v540 = call ptr @mlf_application(ptr %v534, ptr %v539)
  %v541 = call ptr @mlf_constructor(i64 10, i64 1)
  %v542 = call ptr @mlf_constructor(i64 6, i64 0)
  %v543 = call ptr @mlf_application(ptr %v541, ptr %v542)
  %v544 = call ptr @mlf_application(ptr %v540, ptr %v543)
  %v545 = call ptr @mlf_primitive(i64 13)
  %v546 = call ptr @mlf_primitive(i64 12)
  %v547 = call ptr @mlf_application(ptr %v546, ptr %arg)
  %v549 = call ptr @mlf_string(ptr @mlf.bytes.548, i64 1)
  %v550 = call ptr @mlf_application(ptr %v547, ptr %v549)
  %v551 = call ptr @mlf_application(ptr %v545, ptr %v550)
  %v552 = call ptr @mlf_constructor(i64 10, i64 1)
  %v553 = call ptr @mlf_constructor(i64 7, i64 0)
  %v554 = call ptr @mlf_application(ptr %v552, ptr %v553)
  %v555 = call ptr @mlf_application(ptr %v551, ptr %v554)
  %v556 = call ptr @mlf_primitive(i64 13)
  %v557 = call ptr @mlf_primitive(i64 12)
  %v558 = call ptr @mlf_application(ptr %v557, ptr %arg)
  %v560 = call ptr @mlf_string(ptr @mlf.bytes.559, i64 1)
  %v561 = call ptr @mlf_application(ptr %v558, ptr %v560)
  %v562 = call ptr @mlf_application(ptr %v556, ptr %v561)
  %v563 = call ptr @mlf_constructor(i64 10, i64 1)
  %v564 = call ptr @mlf_constructor(i64 8, i64 0)
  %v565 = call ptr @mlf_application(ptr %v563, ptr %v564)
  %v566 = call ptr @mlf_application(ptr %v562, ptr %v565)
  %v567 = call ptr @mlf_primitive(i64 13)
  %v568 = call ptr @mlf_primitive(i64 12)
  %v569 = call ptr @mlf_application(ptr %v568, ptr %arg)
  %v571 = call ptr @mlf_string(ptr @mlf.bytes.570, i64 1)
  %v572 = call ptr @mlf_application(ptr %v569, ptr %v571)
  %v573 = call ptr @mlf_application(ptr %v567, ptr %v572)
  %v574 = call ptr @mlf_constructor(i64 10, i64 1)
  %v575 = call ptr @mlf_constructor(i64 9, i64 0)
  %v576 = call ptr @mlf_application(ptr %v574, ptr %v575)
  %v577 = call ptr @mlf_application(ptr %v573, ptr %v576)
  %v578 = call ptr @mlf_primitive(i64 13)
  %v579 = call ptr @mlf_primitive(i64 12)
  %v580 = call ptr @mlf_application(ptr %v579, ptr %arg)
  %v582 = call ptr @mlf_string(ptr @mlf.bytes.581, i64 0)
  %v583 = call ptr @mlf_application(ptr %v580, ptr %v582)
  %v584 = call ptr @mlf_application(ptr %v578, ptr %v583)
  %v585 = call ptr @mlf_constructor(i64 11, i64 0)
  %v586 = call ptr @mlf_application(ptr %v584, ptr %v585)
  %v587 = call ptr @mlf_constructor(i64 13, i64 0)
  %v588 = call ptr @mlf_application(ptr %v586, ptr %v587)
  %v589 = call ptr @mlf_application(ptr %v577, ptr %v588)
  %v590 = call ptr @mlf_application(ptr %v566, ptr %v589)
  %v591 = call ptr @mlf_application(ptr %v555, ptr %v590)
  %v592 = call ptr @mlf_application(ptr %v544, ptr %v591)
  %v593 = call ptr @mlf_application(ptr %v533, ptr %v592)
  ret ptr %v593
}

define private ptr @mlf.code.598(ptr %env, ptr %arg) {
entry:
  %v599 = call ptr @mlf_env_get(ptr %env, i64 0)
  %v600 = call ptr @mlf_env_get(ptr %env, i64 1)
  %v601 = call ptr @mlf_env_get(ptr %env, i64 2)
  %v602 = call i64 @mlf_tag(ptr %v601)
  switch i64 %v602, label %case.missing.604 [
    i64 15, label %case.603
  ]
case.603:
  %v605 = call ptr @mlf_field(ptr %v601, i64 0)
  %v606 = call ptr @mlf_field(ptr %v601, i64 1)
  %v607 = call ptr @mlf_field(ptr %v601, i64 2)
  %v608 = call ptr @mlf_field(ptr %v601, i64 3)
  %v609 = call i64 @mlf_tag(ptr %v605)
  switch i64 %v609, label %case.missing.611 [
    i64 14, label %case.610
  ]
case.610:
  %v612 = call ptr @mlf_field(ptr %v605, i64 0)
  %v613 = call ptr @mlf_field(ptr %v605, i64 1)
  %v614 = call ptr @mlf_primitive(i64 13)
  %v615 = call ptr @mlf_application(ptr %v599, ptr %arg)
  %v616 = call ptr @mlf_application(ptr %v615, ptr %v612)
  %v617 = call ptr @mlf_application(ptr %v614, ptr %v616)
  %v619 = call ptr @mlf_string(ptr @mlf.bytes.618, i64 1)
  %v620 = call ptr @mlf_application(ptr %v617, ptr %v619)
  %v621 = call ptr @mlf_primitive(i64 13)
  %v622 = call ptr @mlf_application(ptr %v600, ptr %arg)
  %v623 = call ptr @mlf_application(ptr %v622, ptr %v613)
  %v624 = call ptr @mlf_application(ptr %v621, ptr %v623)
  %v626 = call ptr @mlf_string(ptr @mlf.bytes.625, i64 1)
  %v627 = call ptr @mlf_application(ptr %v624, ptr %v626)
  %v628 = call ptr @mlf_primitive(i64 13)
  %v629 = call ptr @mlf_application(ptr %v599, ptr %arg)
  %v630 = call ptr @mlf_application(ptr %v629, ptr %v607)
  %v631 = call ptr @mlf_application(ptr %v628, ptr %v630)
  %v633 = call ptr @mlf_string(ptr @mlf.bytes.632, i64 1)
  %v634 = call ptr @mlf_application(ptr %v631, ptr %v633)
  %v636 = call ptr @mlf_string(ptr @mlf.bytes.635, i64 1)
  %v637 = call ptr @mlf_application(ptr %v634, ptr %v636)
  %v638 = call ptr @mlf_application(ptr %v627, ptr %v637)
  %v639 = call ptr @mlf_application(ptr %v620, ptr %v638)
  ret ptr %v639
case.missing.611:
  call void @mlf_match_failure()
  unreachable
case.missing.604:
  call void @mlf_match_failure()
  unreachable
}

define private ptr @mlf.code.595(ptr %env, ptr %arg) {
entry:
  %v596 = call ptr @mlf_env_get(ptr %env, i64 0)
  %v597 = call ptr @mlf_env_get(ptr %env, i64 1)
  %v640 = call ptr @mlf_env_new(i64 3)
  call void @mlf_env_set(ptr %v640, i64 0, ptr %v596)
  call void @mlf_env_set(ptr %v640, i64 1, ptr %v597)
  call void @mlf_env_set(ptr %v640, i64 2, ptr %arg)
  %v641 = call ptr @mlf_closure(ptr @mlf.code.598, ptr %v640)
  ret ptr %v641
}

define private ptr @mlf.code.644(ptr %env, ptr %arg) {
entry:
  ret ptr %arg
}

define private ptr @mlf.code.650(ptr %env, ptr %arg) {
entry:
  ret ptr %arg
}

define private ptr @mlf.code.658(ptr %env, ptr %arg) {
entry:
  ret ptr %arg
}

define private ptr @mlf.code.661(ptr %env, ptr %arg) {
entry:
  ret ptr %arg
}

define private ptr @mlf.code.668(ptr %env, ptr %arg) {
entry:
  %v669 = call ptr @mlf_env_get(ptr %env, i64 0)
  %v670 = call ptr @mlf_env_get(ptr %env, i64 1)
  %v671 = call ptr @mlf_env_get(ptr %env, i64 2)
  %v672 = call ptr @mlf_env_get(ptr %env, i64 3)
  %v673 = call ptr @mlf_env_get(ptr %env, i64 4)
  %v674 = call ptr @mlf_primitive(i64 13)
  %v675 = call ptr @mlf_primitive(i64 10)
  %v676 = call ptr @mlf_application(ptr %v675, ptr %arg)
  %v677 = call ptr @mlf_application(ptr %v676, ptr %v669)
  %v678 = call ptr @mlf_application(ptr %v674, ptr %v677)
  %v680 = call ptr @mlf_string(ptr @mlf.bytes.679, i64 2)
  %v681 = call ptr @mlf_application(ptr %v678, ptr %v680)
  %v682 = call ptr @mlf_primitive(i64 6)
  %v683 = call ptr @mlf_application(ptr %v670, ptr %v671)
  %v684 = call ptr @mlf_constructor(i64 5, i64 2)
  %v685 = call ptr @mlf_application(ptr %v684, ptr %arg)
  %v686 = call ptr @mlf_application(ptr %v685, ptr %v672)
  %v687 = call ptr @mlf_application(ptr %v683, ptr %v686)
  %v688 = call ptr @mlf_application(ptr %v682, ptr %v687)
  %v689 = call ptr @mlf_primitive(i64 8)
  %v690 = call ptr @mlf_application(ptr %v689, ptr %arg)
  %v692 = call ptr @mlf_integer(ptr @mlf.bytes.691)
  %v693 = call ptr @mlf_application(ptr %v690, ptr %v692)
  %v694 = call ptr @mlf_application(ptr %v673, ptr %v693)
  %v695 = call ptr @mlf_application(ptr %v688, ptr %v694)
  %v696 = call ptr @mlf_application(ptr %v681, ptr %v695)
  ret ptr %v696
}

define private ptr @mlf.code.663(ptr %env, ptr %arg) {
entry:
  %v664 = call ptr @mlf_env_get(ptr %env, i64 0)
  %v665 = call ptr @mlf_env_get(ptr %env, i64 1)
  %v666 = call ptr @mlf_env_get(ptr %env, i64 2)
  %v667 = call ptr @mlf_env_get(ptr %env, i64 3)
  %v697 = call ptr @mlf_env_new(i64 5)
  call void @mlf_env_set(ptr %v697, i64 0, ptr %v664)
  call void @mlf_env_set(ptr %v697, i64 1, ptr %v665)
  call void @mlf_env_set(ptr %v697, i64 2, ptr %v666)
  call void @mlf_env_set(ptr %v697, i64 3, ptr %v667)
  call void @mlf_env_set(ptr %v697, i64 4, ptr %arg)
  %v698 = call ptr @mlf_closure(ptr @mlf.code.668, ptr %v697)
  ret ptr %v698
}

define private ptr @mlf.code.653(ptr %env, ptr %arg) {
entry:
  %v654 = call ptr @mlf_env_get(ptr %env, i64 0)
  %v655 = call ptr @mlf_env_get(ptr %env, i64 1)
  %v656 = call ptr @mlf_env_get(ptr %env, i64 2)
  %v657 = call ptr @mlf_env_get(ptr %env, i64 3)
  %v659 = call ptr @mlf_closure(ptr @mlf.code.658, ptr null)
  %v660 = call ptr @mlf_application(ptr %v659, ptr %arg)
  %v662 = call ptr @mlf_closure(ptr @mlf.code.661, ptr null)
  %v699 = call ptr @mlf_env_new(i64 4)
  call void @mlf_env_set(ptr %v699, i64 0, ptr %v655)
  call void @mlf_env_set(ptr %v699, i64 1, ptr %v656)
  call void @mlf_env_set(ptr %v699, i64 2, ptr %v657)
  call void @mlf_env_set(ptr %v699, i64 3, ptr %v660)
  %v700 = call ptr @mlf_closure(ptr @mlf.code.663, ptr %v699)
  %v701 = call ptr @mlf_application(ptr %v654, ptr %v700)
  %v702 = call ptr @mlf_application(ptr %v662, ptr %v701)
  %v703 = call ptr @mlf_primitive(i64 6)
  %v705 = call ptr @mlf_string(ptr @mlf.bytes.704, i64 1)
  %v706 = call ptr @mlf_application(ptr %v703, ptr %v705)
  %v708 = call ptr @mlf_integer(ptr @mlf.bytes.707)
  %v709 = call ptr @mlf_application(ptr %v702, ptr %v708)
  %v710 = call ptr @mlf_application(ptr %v706, ptr %v709)
  ret ptr %v710
}

define private ptr @mlf.code.646(ptr %env, ptr %arg) {
entry:
  %v647 = call ptr @mlf_env_get(ptr %env, i64 0)
  %v648 = call ptr @mlf_env_get(ptr %env, i64 1)
  %v649 = call ptr @mlf_env_get(ptr %env, i64 2)
  %v651 = call ptr @mlf_closure(ptr @mlf.code.650, ptr null)
  %v652 = call ptr @mlf_application(ptr %v651, ptr %arg)
  %v711 = call ptr @mlf_env_new(i64 4)
  call void @mlf_env_set(ptr %v711, i64 0, ptr %v647)
  call void @mlf_env_set(ptr %v711, i64 1, ptr %v648)
  call void @mlf_env_set(ptr %v711, i64 2, ptr %v649)
  call void @mlf_env_set(ptr %v711, i64 3, ptr %v652)
  %v712 = call ptr @mlf_closure(ptr @mlf.code.653, ptr %v711)
  ret ptr %v712
}

define private ptr @mlf.code.716(ptr %env, ptr %arg) {
entry:
  ret ptr %arg
}

define private ptr @mlf.code.725(ptr %env, ptr %arg) {
entry:
  %v726 = call ptr @mlf_env_get(ptr %env, i64 0)
  %v727 = call ptr @mlf_env_get(ptr %env, i64 1)
  %v728 = call ptr @mlf_env_get(ptr %env, i64 2)
  %v729 = call ptr @mlf_env_get(ptr %env, i64 3)
  %v730 = call ptr @mlf_primitive(i64 13)
  %v731 = call ptr @mlf_primitive(i64 10)
  %v732 = call ptr @mlf_application(ptr %v731, ptr %arg)
  %v733 = call ptr @mlf_application(ptr %v732, ptr %v726)
  %v734 = call ptr @mlf_application(ptr %v730, ptr %v733)
  %v736 = call ptr @mlf_string(ptr @mlf.bytes.735, i64 0)
  %v737 = call ptr @mlf_application(ptr %v734, ptr %v736)
  %v738 = call ptr @mlf_primitive(i64 6)
  %v739 = call ptr @mlf_application(ptr %v727, ptr %v729)
  %v740 = call ptr @mlf_application(ptr %v739, ptr %arg)
  %v741 = call ptr @mlf_application(ptr %v738, ptr %v740)
  %v742 = call ptr @mlf_application(ptr %v728, ptr %v729)
  %v743 = call ptr @mlf_primitive(i64 8)
  %v744 = call ptr @mlf_application(ptr %v743, ptr %arg)
  %v746 = call ptr @mlf_integer(ptr @mlf.bytes.745)
  %v747 = call ptr @mlf_application(ptr %v744, ptr %v746)
  %v748 = call ptr @mlf_application(ptr %v742, ptr %v747)
  %v749 = call ptr @mlf_application(ptr %v741, ptr %v748)
  %v750 = call ptr @mlf_application(ptr %v737, ptr %v749)
  ret ptr %v750
}

define private ptr @mlf.code.721(ptr %env, ptr %arg) {
entry:
  %v722 = call ptr @mlf_env_get(ptr %env, i64 0)
  %v723 = call ptr @mlf_env_get(ptr %env, i64 1)
  %v724 = call ptr @mlf_env_get(ptr %env, i64 2)
  %v751 = call ptr @mlf_env_new(i64 4)
  call void @mlf_env_set(ptr %v751, i64 0, ptr %v722)
  call void @mlf_env_set(ptr %v751, i64 1, ptr %v723)
  call void @mlf_env_set(ptr %v751, i64 2, ptr %v724)
  call void @mlf_env_set(ptr %v751, i64 3, ptr %arg)
  %v752 = call ptr @mlf_closure(ptr @mlf.code.725, ptr %v751)
  ret ptr %v752
}

define private ptr @mlf.code.718(ptr %env, ptr %arg) {
entry:
  %v719 = call ptr @mlf_env_get(ptr %env, i64 0)
  %v720 = call ptr @mlf_env_get(ptr %env, i64 1)
  %v753 = call ptr @mlf_env_new(i64 3)
  call void @mlf_env_set(ptr %v753, i64 0, ptr %v719)
  call void @mlf_env_set(ptr %v753, i64 1, ptr %v720)
  call void @mlf_env_set(ptr %v753, i64 2, ptr %arg)
  %v754 = call ptr @mlf_closure(ptr @mlf.code.721, ptr %v753)
  ret ptr %v754
}

define private ptr @mlf.code.759(ptr %env, ptr %arg) {
entry:
  %v760 = call i64 @mlf_tag(ptr %arg)
  switch i64 %v760, label %case.missing.765 [
    i64 6, label %case.761
    i64 7, label %case.762
    i64 8, label %case.763
    i64 9, label %case.764
  ]
case.761:
  %v767 = call ptr @mlf_string(ptr @mlf.bytes.766, i64 2)
  ret ptr %v767
case.762:
  %v769 = call ptr @mlf_string(ptr @mlf.bytes.768, i64 4)
  ret ptr %v769
case.763:
  %v771 = call ptr @mlf_string(ptr @mlf.bytes.770, i64 4)
  ret ptr %v771
case.764:
  %v773 = call ptr @mlf_string(ptr @mlf.bytes.772, i64 5)
  ret ptr %v773
case.missing.765:
  call void @mlf_match_failure()
  unreachable
}

define private ptr @mlf.code.775(ptr %env, ptr %arg) {
entry:
  ret ptr %arg
}

define private ptr @mlf.code.782(ptr %env, ptr %arg) {
entry:
  ret ptr %arg
}

define private ptr @mlf.code.836(ptr %env, ptr %arg) {
entry:
  %v837 = call ptr @mlf_primitive(i64 3)
  %v839 = call ptr @mlf_string(ptr @mlf.bytes.838, i64 14)
  %v840 = call ptr @mlf_application(ptr %v837, ptr %v839)
  ret ptr %v840
}

define private ptr @mlf.code.823(ptr %env, ptr %arg) {
entry:
  %v824 = call ptr @mlf_env_get(ptr %env, i64 0)
  %v825 = call ptr @mlf_env_get(ptr %env, i64 1)
  %v826 = call ptr @mlf_env_get(ptr %env, i64 2)
  %v827 = call ptr @mlf_env_get(ptr %env, i64 3)
  %v828 = call ptr @mlf_application(ptr %v824, ptr %v825)
  %v829 = call ptr @mlf_primitive(i64 2)
  %v830 = call ptr @mlf_application(ptr %v826, ptr %v827)
  %v832 = call ptr @mlf_integer(ptr @mlf.bytes.831)
  %v833 = call ptr @mlf_application(ptr %v830, ptr %v832)
  %v834 = call ptr @mlf_application(ptr %v829, ptr %v833)
  %v835 = call ptr @mlf_application(ptr %v828, ptr %v834)
  %v841 = call ptr @mlf_closure(ptr @mlf.code.836, ptr null)
  %v842 = call ptr @mlf_application(ptr %v835, ptr %v841)
  ret ptr %v842
}

define private ptr @mlf.code.812(ptr %env, ptr %arg) {
entry:
  %v813 = call ptr @mlf_env_get(ptr %env, i64 0)
  %v814 = call ptr @mlf_env_get(ptr %env, i64 1)
  %v815 = call ptr @mlf_env_get(ptr %env, i64 2)
  %v816 = call ptr @mlf_env_get(ptr %env, i64 3)
  %v817 = call ptr @mlf_application(ptr %v813, ptr %v814)
  %v818 = call ptr @mlf_primitive(i64 3)
  %v820 = call ptr @mlf_string(ptr @mlf.bytes.819, i64 14)
  %v821 = call ptr @mlf_application(ptr %v818, ptr %v820)
  %v822 = call ptr @mlf_application(ptr %v817, ptr %v821)
  %v843 = call ptr @mlf_env_new(i64 4)
  call void @mlf_env_set(ptr %v843, i64 0, ptr %v813)
  call void @mlf_env_set(ptr %v843, i64 1, ptr %v814)
  call void @mlf_env_set(ptr %v843, i64 2, ptr %v815)
  call void @mlf_env_set(ptr %v843, i64 3, ptr %v816)
  %v844 = call ptr @mlf_closure(ptr @mlf.code.823, ptr %v843)
  %v845 = call ptr @mlf_application(ptr %v822, ptr %v844)
  ret ptr %v845
}

define private ptr @mlf.code.777(ptr %env, ptr %arg) {
entry:
  %v778 = call ptr @mlf_env_get(ptr %env, i64 0)
  %v779 = call ptr @mlf_env_get(ptr %env, i64 1)
  %v780 = call ptr @mlf_env_get(ptr %env, i64 2)
  %v781 = call ptr @mlf_env_get(ptr %env, i64 3)
  %v783 = call ptr @mlf_closure(ptr @mlf.code.782, ptr null)
  %v784 = call ptr @mlf_application(ptr %v783, ptr %arg)
  %v785 = call i64 @mlf_tag(ptr %v784)
  switch i64 %v785, label %case.missing.787 [
    i64 15, label %case.786
  ]
case.786:
  %v788 = call ptr @mlf_field(ptr %v784, i64 0)
  %v789 = call ptr @mlf_field(ptr %v784, i64 1)
  %v790 = call ptr @mlf_field(ptr %v784, i64 2)
  %v791 = call ptr @mlf_field(ptr %v784, i64 3)
  %v792 = call ptr @mlf_application(ptr %v778, ptr %v779)
  %v793 = call ptr @mlf_primitive(i64 3)
  %v794 = call ptr @mlf_primitive(i64 6)
  %v796 = call ptr @mlf_string(ptr @mlf.bytes.795, i64 8)
  %v797 = call ptr @mlf_application(ptr %v794, ptr %v796)
  %v798 = call ptr @mlf_primitive(i64 6)
  %v799 = call ptr @mlf_primitive(i64 7)
  %v800 = call ptr @mlf_application(ptr %v799, ptr %v791)
  %v801 = call ptr @mlf_application(ptr %v798, ptr %v800)
  %v802 = call ptr @mlf_primitive(i64 6)
  %v804 = call ptr @mlf_string(ptr @mlf.bytes.803, i64 13)
  %v805 = call ptr @mlf_application(ptr %v802, ptr %v804)
  %v806 = call ptr @mlf_application(ptr %v781, ptr %v789)
  %v807 = call ptr @mlf_application(ptr %v805, ptr %v806)
  %v808 = call ptr @mlf_application(ptr %v801, ptr %v807)
  %v809 = call ptr @mlf_application(ptr %v797, ptr %v808)
  %v810 = call ptr @mlf_application(ptr %v793, ptr %v809)
  %v811 = call ptr @mlf_application(ptr %v792, ptr %v810)
  %v846 = call ptr @mlf_env_new(i64 4)
  call void @mlf_env_set(ptr %v846, i64 0, ptr %v778)
  call void @mlf_env_set(ptr %v846, i64 1, ptr %v779)
  call void @mlf_env_set(ptr %v846, i64 2, ptr %v780)
  call void @mlf_env_set(ptr %v846, i64 3, ptr %v784)
  %v847 = call ptr @mlf_closure(ptr @mlf.code.812, ptr %v846)
  %v848 = call ptr @mlf_application(ptr %v811, ptr %v847)
  ret ptr %v848
case.missing.787:
  call void @mlf_match_failure()
  unreachable
}

define private ptr @mlf.code.852(ptr %env, ptr %arg) {
entry:
  ret ptr %arg
}

define private ptr @mlf.code.907(ptr %env, ptr %arg) {
entry:
  %v908 = call ptr @mlf_env_get(ptr %env, i64 0)
  %v909 = call ptr @mlf_env_get(ptr %env, i64 1)
  %v910 = call ptr @mlf_env_get(ptr %env, i64 2)
  %v911 = call ptr @mlf_application(ptr %v908, ptr %arg)
  %v912 = call ptr @mlf_application(ptr %v911, ptr %v910)
  %v913 = call i64 @mlf_tag(ptr %v912)
  switch i64 %v913, label %case.missing.917 [
    i64 16, label %case.914
    i64 17, label %case.915
    i64 18, label %case.916
  ]
case.914:
  %v918 = call ptr @mlf_field(ptr %v912, i64 0)
  %v919 = call ptr @mlf_application(ptr %v909, ptr %v918)
  ret ptr %v919
case.915:
  %v920 = call ptr @mlf_field(ptr %v912, i64 0)
  %v921 = call ptr @mlf_field(ptr %v912, i64 1)
  %v922 = call ptr @mlf_primitive(i64 3)
  %v923 = call ptr @mlf_primitive(i64 6)
  %v925 = call ptr @mlf_string(ptr @mlf.bytes.924, i64 15)
  %v926 = call ptr @mlf_application(ptr %v923, ptr %v925)
  %v927 = call ptr @mlf_primitive(i64 6)
  %v928 = call ptr @mlf_application(ptr %v927, ptr %v920)
  %v929 = call ptr @mlf_primitive(i64 6)
  %v931 = call ptr @mlf_string(ptr @mlf.bytes.930, i64 9)
  %v932 = call ptr @mlf_application(ptr %v929, ptr %v931)
  %v933 = call ptr @mlf_primitive(i64 7)
  %v934 = call ptr @mlf_application(ptr %v933, ptr %v921)
  %v935 = call ptr @mlf_application(ptr %v932, ptr %v934)
  %v936 = call ptr @mlf_application(ptr %v928, ptr %v935)
  %v937 = call ptr @mlf_application(ptr %v926, ptr %v936)
  %v938 = call ptr @mlf_application(ptr %v922, ptr %v937)
  ret ptr %v938
case.916:
  %v939 = call ptr @mlf_field(ptr %v912, i64 0)
  %v940 = call ptr @mlf_primitive(i64 3)
  %v941 = call ptr @mlf_primitive(i64 6)
  %v943 = call ptr @mlf_string(ptr @mlf.bytes.942, i64 29)
  %v944 = call ptr @mlf_application(ptr %v941, ptr %v943)
  %v945 = call ptr @mlf_primitive(i64 7)
  %v946 = call ptr @mlf_application(ptr %v945, ptr %v939)
  %v947 = call ptr @mlf_application(ptr %v944, ptr %v946)
  %v948 = call ptr @mlf_application(ptr %v940, ptr %v947)
  ret ptr %v948
case.missing.917:
  call void @mlf_match_failure()
  unreachable
}

define private ptr @mlf.code.973(ptr %env, ptr %arg) {
entry:
  %v974 = call ptr @mlf_env_get(ptr %env, i64 0)
  %v975 = call ptr @mlf_env_get(ptr %env, i64 1)
  %v976 = call ptr @mlf_application(ptr %v974, ptr %v975)
  ret ptr %v976
}

define private ptr @mlf.code.893(ptr %env, ptr %arg) {
entry:
  %v894 = call ptr @mlf_env_get(ptr %env, i64 0)
  %v895 = call ptr @mlf_env_get(ptr %env, i64 1)
  %v896 = call ptr @mlf_env_get(ptr %env, i64 2)
  %v897 = call ptr @mlf_env_get(ptr %env, i64 3)
  %v898 = call ptr @mlf_env_get(ptr %env, i64 4)
  %v899 = call ptr @mlf_env_get(ptr %env, i64 5)
  %v900 = call i64 @mlf_tag(ptr %v899)
  switch i64 %v900, label %case.missing.902 [
    i64 15, label %case.901
  ]
case.901:
  %v903 = call ptr @mlf_field(ptr %v899, i64 0)
  %v904 = call ptr @mlf_field(ptr %v899, i64 1)
  %v905 = call ptr @mlf_field(ptr %v899, i64 2)
  %v906 = call ptr @mlf_field(ptr %v899, i64 3)
  %v949 = call ptr @mlf_env_new(i64 3)
  call void @mlf_env_set(ptr %v949, i64 0, ptr %v896)
  call void @mlf_env_set(ptr %v949, i64 1, ptr %v898)
  call void @mlf_env_set(ptr %v949, i64 2, ptr %v899)
  %v950 = call ptr @mlf_closure(ptr @mlf.code.907, ptr %v949)
  %v951 = call ptr @mlf_application(ptr %v897, ptr %arg)
  %v952 = call i64 @mlf_tag(ptr %v951)
  switch i64 %v952, label %case.missing.957 [
    i64 12, label %case.953
    i64 13, label %case.954
    i64 11, label %case.955
    i64 10, label %case.956
  ]
case.953:
  %v958 = call ptr @mlf_primitive(i64 3)
  %v959 = call ptr @mlf_primitive(i64 6)
  %v961 = call ptr @mlf_string(ptr @mlf.bytes.960, i64 16)
  %v962 = call ptr @mlf_application(ptr %v959, ptr %v961)
  %v963 = call ptr @mlf_primitive(i64 7)
  %v964 = call ptr @mlf_application(ptr %v963, ptr %v906)
  %v965 = call ptr @mlf_application(ptr %v962, ptr %v964)
  %v966 = call ptr @mlf_application(ptr %v958, ptr %v965)
  ret ptr %v966
case.954:
  %v967 = call ptr @mlf_application(ptr %v894, ptr %v895)
  %v968 = call ptr @mlf_primitive(i64 3)
  %v970 = call ptr @mlf_string(ptr @mlf.bytes.969, i64 42)
  %v971 = call ptr @mlf_application(ptr %v968, ptr %v970)
  %v972 = call ptr @mlf_application(ptr %v967, ptr %v971)
  %v977 = call ptr @mlf_env_new(i64 2)
  call void @mlf_env_set(ptr %v977, i64 0, ptr %v898)
  call void @mlf_env_set(ptr %v977, i64 1, ptr %v899)
  %v978 = call ptr @mlf_closure(ptr @mlf.code.973, ptr %v977)
  %v979 = call ptr @mlf_application(ptr %v972, ptr %v978)
  ret ptr %v979
case.955:
  %v980 = call ptr @mlf_application(ptr %v950, ptr %v904)
  ret ptr %v980
case.956:
  %v981 = call ptr @mlf_field(ptr %v951, i64 0)
  %v982 = call ptr @mlf_application(ptr %v950, ptr %v981)
  ret ptr %v982
case.missing.957:
  call void @mlf_match_failure()
  unreachable
case.missing.902:
  call void @mlf_match_failure()
  unreachable
}

define private ptr @mlf.code.883(ptr %env, ptr %arg) {
entry:
  %v884 = call ptr @mlf_env_get(ptr %env, i64 0)
  %v885 = call ptr @mlf_env_get(ptr %env, i64 1)
  %v886 = call ptr @mlf_env_get(ptr %env, i64 2)
  %v887 = call ptr @mlf_env_get(ptr %env, i64 3)
  %v888 = call ptr @mlf_env_get(ptr %env, i64 4)
  %v889 = call ptr @mlf_env_get(ptr %env, i64 5)
  %v890 = call ptr @mlf_application(ptr %v884, ptr %v885)
  %v891 = call ptr @mlf_primitive(i64 4)
  %v892 = call ptr @mlf_application(ptr %v890, ptr %v891)
  %v983 = call ptr @mlf_env_new(i64 6)
  call void @mlf_env_set(ptr %v983, i64 0, ptr %v884)
  call void @mlf_env_set(ptr %v983, i64 1, ptr %v885)
  call void @mlf_env_set(ptr %v983, i64 2, ptr %v886)
  call void @mlf_env_set(ptr %v983, i64 3, ptr %v887)
  call void @mlf_env_set(ptr %v983, i64 4, ptr %v888)
  call void @mlf_env_set(ptr %v983, i64 5, ptr %v889)
  %v984 = call ptr @mlf_closure(ptr @mlf.code.893, ptr %v983)
  %v985 = call ptr @mlf_application(ptr %v892, ptr %v984)
  ret ptr %v985
}

define private ptr @mlf.code.870(ptr %env, ptr %arg) {
entry:
  %v871 = call ptr @mlf_env_get(ptr %env, i64 0)
  %v872 = call ptr @mlf_env_get(ptr %env, i64 1)
  %v873 = call ptr @mlf_env_get(ptr %env, i64 2)
  %v874 = call ptr @mlf_env_get(ptr %env, i64 3)
  %v875 = call ptr @mlf_env_get(ptr %env, i64 4)
  %v876 = call ptr @mlf_env_get(ptr %env, i64 5)
  %v877 = call ptr @mlf_application(ptr %v871, ptr %v872)
  %v878 = call ptr @mlf_primitive(i64 2)
  %v880 = call ptr @mlf_string(ptr @mlf.bytes.879, i64 26)
  %v881 = call ptr @mlf_application(ptr %v878, ptr %v880)
  %v882 = call ptr @mlf_application(ptr %v877, ptr %v881)
  %v986 = call ptr @mlf_env_new(i64 6)
  call void @mlf_env_set(ptr %v986, i64 0, ptr %v871)
  call void @mlf_env_set(ptr %v986, i64 1, ptr %v872)
  call void @mlf_env_set(ptr %v986, i64 2, ptr %v873)
  call void @mlf_env_set(ptr %v986, i64 3, ptr %v874)
  call void @mlf_env_set(ptr %v986, i64 4, ptr %v875)
  call void @mlf_env_set(ptr %v986, i64 5, ptr %v876)
  %v987 = call ptr @mlf_closure(ptr @mlf.code.883, ptr %v986)
  %v988 = call ptr @mlf_application(ptr %v882, ptr %v987)
  ret ptr %v988
}

define private ptr @mlf.code.860(ptr %env, ptr %arg) {
entry:
  %v861 = call ptr @mlf_env_get(ptr %env, i64 0)
  %v862 = call ptr @mlf_env_get(ptr %env, i64 1)
  %v863 = call ptr @mlf_env_get(ptr %env, i64 2)
  %v864 = call ptr @mlf_env_get(ptr %env, i64 3)
  %v865 = call ptr @mlf_env_get(ptr %env, i64 4)
  %v866 = call ptr @mlf_env_get(ptr %env, i64 5)
  %v867 = call ptr @mlf_application(ptr %v861, ptr %v862)
  %v868 = call ptr @mlf_application(ptr %v865, ptr %arg)
  %v869 = call ptr @mlf_application(ptr %v867, ptr %v868)
  %v989 = call ptr @mlf_env_new(i64 6)
  call void @mlf_env_set(ptr %v989, i64 0, ptr %v861)
  call void @mlf_env_set(ptr %v989, i64 1, ptr %v862)
  call void @mlf_env_set(ptr %v989, i64 2, ptr %v863)
  call void @mlf_env_set(ptr %v989, i64 3, ptr %v864)
  call void @mlf_env_set(ptr %v989, i64 4, ptr %v866)
  call void @mlf_env_set(ptr %v989, i64 5, ptr %arg)
  %v990 = call ptr @mlf_closure(ptr @mlf.code.870, ptr %v989)
  %v991 = call ptr @mlf_application(ptr %v869, ptr %v990)
  ret ptr %v991
}

define private ptr @mlf.code.854(ptr %env, ptr %arg) {
entry:
  %v855 = call ptr @mlf_env_get(ptr %env, i64 0)
  %v856 = call ptr @mlf_env_get(ptr %env, i64 1)
  %v857 = call ptr @mlf_env_get(ptr %env, i64 2)
  %v858 = call ptr @mlf_env_get(ptr %env, i64 3)
  %v859 = call ptr @mlf_env_get(ptr %env, i64 4)
  %v992 = call ptr @mlf_env_new(i64 6)
  call void @mlf_env_set(ptr %v992, i64 0, ptr %v855)
  call void @mlf_env_set(ptr %v992, i64 1, ptr %v856)
  call void @mlf_env_set(ptr %v992, i64 2, ptr %v857)
  call void @mlf_env_set(ptr %v992, i64 3, ptr %v858)
  call void @mlf_env_set(ptr %v992, i64 4, ptr %v859)
  call void @mlf_env_set(ptr %v992, i64 5, ptr %arg)
  %v993 = call ptr @mlf_closure(ptr @mlf.code.860, ptr %v992)
  ret ptr %v993
}

define private ptr @mlf.code.1072(ptr %env, ptr %arg) {
entry:
  %v1073 = call ptr @mlf_env_get(ptr %env, i64 0)
  %v1074 = call ptr @mlf_env_get(ptr %env, i64 1)
  %v1075 = call ptr @mlf_application(ptr %v1073, ptr %v1074)
  ret ptr %v1075
}

define private ptr @mlf.code.1061(ptr %env, ptr %arg) {
entry:
  %v1062 = call ptr @mlf_env_get(ptr %env, i64 0)
  %v1063 = call ptr @mlf_env_get(ptr %env, i64 1)
  %v1064 = call ptr @mlf_env_get(ptr %env, i64 2)
  %v1065 = call ptr @mlf_env_get(ptr %env, i64 3)
  %v1066 = call ptr @mlf_application(ptr %v1062, ptr %v1063)
  %v1067 = call ptr @mlf_primitive(i64 3)
  %v1069 = call ptr @mlf_string(ptr @mlf.bytes.1068, i64 77)
  %v1070 = call ptr @mlf_application(ptr %v1067, ptr %v1069)
  %v1071 = call ptr @mlf_application(ptr %v1066, ptr %v1070)
  %v1076 = call ptr @mlf_env_new(i64 2)
  call void @mlf_env_set(ptr %v1076, i64 0, ptr %v1064)
  call void @mlf_env_set(ptr %v1076, i64 1, ptr %v1065)
  %v1077 = call ptr @mlf_closure(ptr @mlf.code.1072, ptr %v1076)
  %v1078 = call ptr @mlf_application(ptr %v1071, ptr %v1077)
  ret ptr %v1078
}

define private ptr @mlf.code.1050(ptr %env, ptr %arg) {
entry:
  %v1051 = call ptr @mlf_env_get(ptr %env, i64 0)
  %v1052 = call ptr @mlf_env_get(ptr %env, i64 1)
  %v1053 = call ptr @mlf_env_get(ptr %env, i64 2)
  %v1054 = call ptr @mlf_env_get(ptr %env, i64 3)
  %v1055 = call ptr @mlf_application(ptr %v1051, ptr %v1052)
  %v1056 = call ptr @mlf_primitive(i64 3)
  %v1058 = call ptr @mlf_string(ptr @mlf.bytes.1057, i64 72)
  %v1059 = call ptr @mlf_application(ptr %v1056, ptr %v1058)
  %v1060 = call ptr @mlf_application(ptr %v1055, ptr %v1059)
  %v1079 = call ptr @mlf_env_new(i64 4)
  call void @mlf_env_set(ptr %v1079, i64 0, ptr %v1051)
  call void @mlf_env_set(ptr %v1079, i64 1, ptr %v1052)
  call void @mlf_env_set(ptr %v1079, i64 2, ptr %v1053)
  call void @mlf_env_set(ptr %v1079, i64 3, ptr %v1054)
  %v1080 = call ptr @mlf_closure(ptr @mlf.code.1061, ptr %v1079)
  %v1081 = call ptr @mlf_application(ptr %v1060, ptr %v1080)
  ret ptr %v1081
}

define private ptr @mlf.code.0(ptr %env, ptr %arg) {
entry:
  %v1 = call ptr @mlf_hole()
  %v2 = call ptr @mlf_hole()
  %v3 = call ptr @mlf_hole()
  %v5 = call ptr @mlf_closure(ptr @mlf.code.4, ptr null)
  %v14 = call ptr @mlf_closure(ptr @mlf.code.6, ptr null)
  %v15 = call ptr @mlf_application(ptr %v5, ptr %v14)
  call void @mlf_fill(ptr %v1, ptr %v15)
  %v17 = call ptr @mlf_closure(ptr @mlf.code.16, ptr null)
  %v26 = call ptr @mlf_closure(ptr @mlf.code.18, ptr null)
  %v27 = call ptr @mlf_application(ptr %v17, ptr %v26)
  call void @mlf_fill(ptr %v2, ptr %v27)
  %v29 = call ptr @mlf_closure(ptr @mlf.code.28, ptr null)
  %v30 = call ptr @mlf_constructor(i64 20, i64 2)
  %v32 = call ptr @mlf_closure(ptr @mlf.code.31, ptr null)
  %v33 = call ptr @mlf_primitive(i64 0)
  %v34 = call ptr @mlf_application(ptr %v32, ptr %v33)
  %v35 = call ptr @mlf_application(ptr %v30, ptr %v34)
  %v37 = call ptr @mlf_closure(ptr @mlf.code.36, ptr null)
  %v38 = call ptr @mlf_primitive(i64 1)
  %v39 = call ptr @mlf_application(ptr %v37, ptr %v38)
  %v40 = call ptr @mlf_application(ptr %v35, ptr %v39)
  %v41 = call ptr @mlf_application(ptr %v29, ptr %v40)
  call void @mlf_fill(ptr %v3, ptr %v41)
  %v43 = call ptr @mlf_closure(ptr @mlf.code.42, ptr null)
  %v61 = call ptr @mlf_closure(ptr @mlf.code.44, ptr null)
  %v62 = call ptr @mlf_application(ptr %v43, ptr %v61)
  %v64 = call ptr @mlf_integer(ptr @mlf.bytes.63)
  %v66 = call ptr @mlf_integer(ptr @mlf.bytes.65)
  %v77 = call ptr @mlf_closure(ptr @mlf.code.67, ptr null)
  %v88 = call ptr @mlf_closure(ptr @mlf.code.78, ptr null)
  %v114 = call ptr @mlf_env_new(i64 1)
  call void @mlf_env_set(ptr %v114, i64 0, ptr %v77)
  %v115 = call ptr @mlf_closure(ptr @mlf.code.89, ptr %v114)
  %v117 = call ptr @mlf_closure(ptr @mlf.code.116, ptr null)
  %v147 = call ptr @mlf_env_new(i64 2)
  call void @mlf_env_set(ptr %v147, i64 0, ptr %v88)
  call void @mlf_env_set(ptr %v147, i64 1, ptr %v115)
  %v148 = call ptr @mlf_closure(ptr @mlf.code.118, ptr %v147)
  %v149 = call ptr @mlf_application(ptr %v62, ptr %v148)
  %v150 = call ptr @mlf_application(ptr %v117, ptr %v149)
  %v152 = call ptr @mlf_closure(ptr @mlf.code.151, ptr null)
  %v176 = call ptr @mlf_closure(ptr @mlf.code.153, ptr null)
  %v177 = call ptr @mlf_application(ptr %v62, ptr %v176)
  %v178 = call ptr @mlf_application(ptr %v152, ptr %v177)
  %v227 = call ptr @mlf_closure(ptr @mlf.code.179, ptr null)
  %v263 = call ptr @mlf_closure(ptr @mlf.code.228, ptr null)
  %v295 = call ptr @mlf_env_new(i64 3)
  call void @mlf_env_set(ptr %v295, i64 0, ptr %v64)
  call void @mlf_env_set(ptr %v295, i64 1, ptr %v66)
  call void @mlf_env_set(ptr %v295, i64 2, ptr %v88)
  %v296 = call ptr @mlf_closure(ptr @mlf.code.264, ptr %v295)
  %v298 = call ptr @mlf_closure(ptr @mlf.code.297, ptr null)
  %v391 = call ptr @mlf_env_new(i64 4)
  call void @mlf_env_set(ptr %v391, i64 0, ptr %v62)
  call void @mlf_env_set(ptr %v391, i64 1, ptr %v64)
  call void @mlf_env_set(ptr %v391, i64 2, ptr %v66)
  call void @mlf_env_set(ptr %v391, i64 3, ptr %v150)
  %v392 = call ptr @mlf_closure(ptr @mlf.code.299, ptr %v391)
  %v393 = call ptr @mlf_application(ptr %v298, ptr %v392)
  %v395 = call ptr @mlf_closure(ptr @mlf.code.394, ptr null)
  %v521 = call ptr @mlf_env_new(i64 7)
  call void @mlf_env_set(ptr %v521, i64 0, ptr %v115)
  call void @mlf_env_set(ptr %v521, i64 1, ptr %v150)
  call void @mlf_env_set(ptr %v521, i64 2, ptr %v178)
  call void @mlf_env_set(ptr %v521, i64 3, ptr %v227)
  call void @mlf_env_set(ptr %v521, i64 4, ptr %v263)
  call void @mlf_env_set(ptr %v521, i64 5, ptr %v296)
  call void @mlf_env_set(ptr %v521, i64 6, ptr %v393)
  %v522 = call ptr @mlf_closure(ptr @mlf.code.396, ptr %v521)
  %v523 = call ptr @mlf_application(ptr %v395, ptr %v522)
  %v594 = call ptr @mlf_closure(ptr @mlf.code.524, ptr null)
  %v642 = call ptr @mlf_env_new(i64 2)
  call void @mlf_env_set(ptr %v642, i64 0, ptr %v115)
  call void @mlf_env_set(ptr %v642, i64 1, ptr %v150)
  %v643 = call ptr @mlf_closure(ptr @mlf.code.595, ptr %v642)
  %v645 = call ptr @mlf_closure(ptr @mlf.code.644, ptr null)
  %v713 = call ptr @mlf_env_new(i64 3)
  call void @mlf_env_set(ptr %v713, i64 0, ptr %v62)
  call void @mlf_env_set(ptr %v713, i64 1, ptr %v64)
  call void @mlf_env_set(ptr %v713, i64 2, ptr %v643)
  %v714 = call ptr @mlf_closure(ptr @mlf.code.646, ptr %v713)
  %v715 = call ptr @mlf_application(ptr %v645, ptr %v714)
  %v717 = call ptr @mlf_closure(ptr @mlf.code.716, ptr null)
  %v755 = call ptr @mlf_env_new(i64 2)
  call void @mlf_env_set(ptr %v755, i64 0, ptr %v66)
  call void @mlf_env_set(ptr %v755, i64 1, ptr %v715)
  %v756 = call ptr @mlf_closure(ptr @mlf.code.718, ptr %v755)
  %v757 = call ptr @mlf_application(ptr %v62, ptr %v756)
  %v758 = call ptr @mlf_application(ptr %v717, ptr %v757)
  %v774 = call ptr @mlf_closure(ptr @mlf.code.759, ptr null)
  %v776 = call ptr @mlf_closure(ptr @mlf.code.775, ptr null)
  %v849 = call ptr @mlf_env_new(i64 4)
  call void @mlf_env_set(ptr %v849, i64 0, ptr %v2)
  call void @mlf_env_set(ptr %v849, i64 1, ptr %v3)
  call void @mlf_env_set(ptr %v849, i64 2, ptr %v758)
  call void @mlf_env_set(ptr %v849, i64 3, ptr %v774)
  %v850 = call ptr @mlf_closure(ptr @mlf.code.777, ptr %v849)
  %v851 = call ptr @mlf_application(ptr %v776, ptr %v850)
  %v853 = call ptr @mlf_closure(ptr @mlf.code.852, ptr null)
  %v994 = call ptr @mlf_env_new(i64 5)
  call void @mlf_env_set(ptr %v994, i64 0, ptr %v2)
  call void @mlf_env_set(ptr %v994, i64 1, ptr %v3)
  call void @mlf_env_set(ptr %v994, i64 2, ptr %v523)
  call void @mlf_env_set(ptr %v994, i64 3, ptr %v594)
  call void @mlf_env_set(ptr %v994, i64 4, ptr %v851)
  %v995 = call ptr @mlf_closure(ptr @mlf.code.854, ptr %v994)
  %v996 = call ptr @mlf_application(ptr %v62, ptr %v995)
  %v997 = call ptr @mlf_application(ptr %v853, ptr %v996)
  %v998 = call ptr @mlf_constructor(i64 15, i64 4)
  %v999 = call ptr @mlf_constructor(i64 14, i64 2)
  %v1000 = call ptr @mlf_constructor(i64 5, i64 2)
  %v1002 = call ptr @mlf_integer(ptr @mlf.bytes.1001)
  %v1003 = call ptr @mlf_application(ptr %v1000, ptr %v1002)
  %v1005 = call ptr @mlf_integer(ptr @mlf.bytes.1004)
  %v1006 = call ptr @mlf_application(ptr %v1003, ptr %v1005)
  %v1007 = call ptr @mlf_application(ptr %v999, ptr %v1006)
  %v1008 = call ptr @mlf_constructor(i64 2, i64 2)
  %v1009 = call ptr @mlf_constructor(i64 5, i64 2)
  %v1011 = call ptr @mlf_integer(ptr @mlf.bytes.1010)
  %v1012 = call ptr @mlf_application(ptr %v1009, ptr %v1011)
  %v1014 = call ptr @mlf_integer(ptr @mlf.bytes.1013)
  %v1015 = call ptr @mlf_application(ptr %v1012, ptr %v1014)
  %v1016 = call ptr @mlf_application(ptr %v1008, ptr %v1015)
  %v1017 = call ptr @mlf_constructor(i64 2, i64 2)
  %v1018 = call ptr @mlf_constructor(i64 5, i64 2)
  %v1020 = call ptr @mlf_integer(ptr @mlf.bytes.1019)
  %v1021 = call ptr @mlf_application(ptr %v1018, ptr %v1020)
  %v1023 = call ptr @mlf_integer(ptr @mlf.bytes.1022)
  %v1024 = call ptr @mlf_application(ptr %v1021, ptr %v1023)
  %v1025 = call ptr @mlf_application(ptr %v1017, ptr %v1024)
  %v1026 = call ptr @mlf_constructor(i64 1, i64 0)
  %v1027 = call ptr @mlf_application(ptr %v1025, ptr %v1026)
  %v1028 = call ptr @mlf_application(ptr %v1016, ptr %v1027)
  %v1029 = call ptr @mlf_application(ptr %v1007, ptr %v1028)
  %v1030 = call ptr @mlf_application(ptr %v998, ptr %v1029)
  %v1031 = call ptr @mlf_constructor(i64 9, i64 0)
  %v1032 = call ptr @mlf_application(ptr %v1030, ptr %v1031)
  %v1033 = call ptr @mlf_constructor(i64 5, i64 2)
  %v1035 = call ptr @mlf_integer(ptr @mlf.bytes.1034)
  %v1036 = call ptr @mlf_application(ptr %v1033, ptr %v1035)
  %v1038 = call ptr @mlf_integer(ptr @mlf.bytes.1037)
  %v1039 = call ptr @mlf_application(ptr %v1036, ptr %v1038)
  %v1040 = call ptr @mlf_application(ptr %v1032, ptr %v1039)
  %v1042 = call ptr @mlf_integer(ptr @mlf.bytes.1041)
  %v1043 = call ptr @mlf_application(ptr %v1040, ptr %v1042)
  %v1044 = call ptr @mlf_application(ptr %v2, ptr %v3)
  %v1045 = call ptr @mlf_primitive(i64 3)
  %v1047 = call ptr @mlf_string(ptr @mlf.bytes.1046, i64 52)
  %v1048 = call ptr @mlf_application(ptr %v1045, ptr %v1047)
  %v1049 = call ptr @mlf_application(ptr %v1044, ptr %v1048)
  %v1082 = call ptr @mlf_env_new(i64 4)
  call void @mlf_env_set(ptr %v1082, i64 0, ptr %v2)
  call void @mlf_env_set(ptr %v1082, i64 1, ptr %v3)
  call void @mlf_env_set(ptr %v1082, i64 2, ptr %v997)
  call void @mlf_env_set(ptr %v1082, i64 3, ptr %v1043)
  %v1083 = call ptr @mlf_closure(ptr @mlf.code.1050, ptr %v1082)
  %v1084 = call ptr @mlf_application(ptr %v1049, ptr %v1083)
  ret ptr %v1084
}

define ptr @mlf_entry() {
  %root = call ptr @mlf.code.0(ptr null, ptr null)
  ret ptr %root
}
define i32 @main() {
  %root = call ptr @mlf_entry()
  %status = call i32 @mlf_run(ptr %root, i64 1)
  ret i32 %status
}
