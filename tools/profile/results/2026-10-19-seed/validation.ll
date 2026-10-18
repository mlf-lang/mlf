; Generated from independently checked xMLF.
source_filename = "emlf"

declare ptr @mlf_execute_st_lazy(ptr)
declare ptr @mlf_st_new_array(ptr, ptr)
declare ptr @mlf_st_read_array(ptr, ptr)
declare ptr @mlf_st_write_array(ptr, ptr, ptr)
declare ptr @mlf_st_length_array(ptr)
declare void @mlf_set_args(i32, ptr)
declare ptr @mlf_env_new(i64)
declare void @mlf_env_set(ptr, i64, ptr)
declare ptr @mlf_env_get(ptr, i64)
declare ptr @mlf_thunk(ptr, ptr)
declare ptr @mlf_closure(ptr, ptr)
declare ptr @mlf_application(ptr, ptr)
declare ptr @mlf_hole()
declare void @mlf_fill(ptr, ptr)
declare ptr @mlf_integer(ptr)
declare ptr @mlf_string(ptr, i64)
declare ptr @mlf_double(double)
declare double @llvm.sqrt.f64(double)
declare double @mlf_int_to_double(ptr)
declare ptr @mlf_read_int_table(ptr, ptr)
declare ptr @mlf_write_int_table(ptr, ptr, ptr)
declare ptr @mlf_add_int_table(ptr, ptr, ptr)
declare void @mlf_roots_enter(ptr, i64, ptr)
declare void @mlf_roots_leave(ptr)
declare void @mlf_gc_check(i64, ptr)
declare ptr @mlf_get_byte_line()
declare ptr @mlf_new_array(i64, ptr, ptr)
declare ptr @mlf_bytes_from_string(ptr)
declare ptr @mlf_put_bytes(ptr, ptr, ptr)
declare ptr @mlf_new_int_table()
declare void @llvm.memmove.p0.p0.i64(ptr, ptr, i64, i1)
declare i8 @mlf_byte(ptr)
declare ptr @mlf_peek(ptr)
declare ptr @mlf_native_io(ptr, ptr)
declare void @mlf_bounds_failure() noreturn
declare ptr @mlf_primitive(i64)
declare ptr @mlf_prim1(i64, ptr)
declare ptr @mlf_prim2(i64, ptr, ptr)
declare i64 @mlf_truth(ptr)
declare ptr @mlf_prim3(i64, ptr, ptr, ptr)
declare ptr @mlf_force(ptr)
declare ptr @mlf_add_int(ptr, ptr)
declare ptr @mlf_sub_int(ptr, ptr)
declare ptr @mlf_eq_int(ptr, ptr)
declare ptr @mlf_lt_int(ptr, ptr)
declare ptr @mlf_constructor(i64, i64)
declare ptr @mlf_constructor1(i64, ptr)
declare ptr @mlf_constructor2(i64, ptr, ptr)
declare ptr @mlf_constructor_fields(i64, ptr)
declare ptr @mlf_constructor_new(i64, i64)
declare ptr @mlf_field(ptr, i64)
declare void @mlf_match_failure() noreturn
declare { i64, i1 } @llvm.sadd.with.overflow.i64(i64, i64)
declare { i64, i1 } @llvm.smul.with.overflow.i64(i64, i64)
declare { i64, i1 } @llvm.ssub.with.overflow.i64(i64, i64)
declare i32 @mlf_run(ptr, i64)

!0 = !{!"MLF storage"}
!1 = !{!"managed object", !0}
!2 = !{!"array cells", !0}
!3 = !{!1, !1, i64 0}
!4 = !{!2, !2, i64 0}
define private ptr @mlf.code.1(ptr %env, ptr %arg) {
entry:
  %v2 = call ptr @mlf_double(double 0x4010000000000000)
  %v3 = call ptr @mlf_double(double 0x400921fb54442d18)
  %v4 = getelementptr i8, ptr %v2, i64 24
  %v5 = load double, ptr %v4, align 8, !tbaa !3
  %v6 = getelementptr i8, ptr %v3, i64 24
  %v7 = load double, ptr %v6, align 8, !tbaa !3
  %v8 = fmul double %v5, %v7
  %v9 = call ptr @mlf_double(double %v8)
  %v10 = call ptr @mlf_double(double 0x400921fb54442d18)
  %v11 = getelementptr i8, ptr %v9, i64 24
  %v12 = load double, ptr %v11, align 8, !tbaa !3
  %v13 = getelementptr i8, ptr %v10, i64 24
  %v14 = load double, ptr %v13, align 8, !tbaa !3
  %v15 = fmul double %v12, %v14
  %v16 = call ptr @mlf_double(double %v15)
  ret ptr %v16
}

define private ptr @mlf.code.22(ptr %env, ptr %arg) {
entry:
  %v23 = call ptr @mlf_double(double 0x0000000000000000)
  %v24 = call ptr @mlf_prim2(i64 31, ptr inttoptr (i64 71 to ptr), ptr %v23)
  ret ptr %v24
}

define private ptr @mlf.code.41(ptr %env, ptr %arg) {
entry:
  %v42 = ptrtoint ptr inttoptr (i64 1 to ptr) to i64
  %v43 = ptrtoint ptr inttoptr (i64 13 to ptr) to i64
  %v44 = and i64 %v42, %v43
  %v45 = and i64 %v44, 1
  %v46 = icmp ne i64 %v45, 0
  br i1 %v46, label %yes.47, label %no.48
yes.47:
  %v50 = sub i64 %v43, 1
  %v51 = call { i64, i1 } @llvm.sadd.with.overflow.i64(i64 %v42, i64 %v50)
  %v52 = extractvalue { i64, i1 } %v51, 0
  %v53 = extractvalue { i64, i1 } %v51, 1
  br i1 %v53, label %yes.54, label %no.55
yes.54:
  %v57 = call ptr @mlf_add_int(ptr inttoptr (i64 1 to ptr), ptr inttoptr (i64 13 to ptr))
  br label %join.56
no.55:
  %v58 = inttoptr i64 %v52 to ptr
  br label %join.56
join.56:
  %v59 = phi ptr [ %v57, %yes.54 ], [ %v58, %no.55 ]
  br label %join.49
no.48:
  %v60 = call ptr @mlf_add_int(ptr inttoptr (i64 1 to ptr), ptr inttoptr (i64 13 to ptr))
  br label %join.49
join.49:
  %v61 = phi ptr [ %v59, %join.56 ], [ %v60, %no.48 ]
  ret ptr %v61
}

define private ptr @mlf.code.36(ptr %env, ptr %arg) {
entry:
  %v37 = getelementptr i8, ptr %env, i64 24
  %v38 = load ptr, ptr %v37, align 8, !tbaa !3
  %v39 = getelementptr i8, ptr %env, i64 32
  %v40 = load ptr, ptr %v39, align 8, !tbaa !3
  %v62 = call ptr @mlf_thunk(ptr @mlf.code.41, ptr null)
  %v63 = call ptr @mlf_prim3(i64 33, ptr %v40, ptr %v62, ptr %v38)
  ret ptr %v63
}

define private ptr @mlf.code.76(ptr %env, ptr %arg) {
entry:
  %v77 = ptrtoint ptr inttoptr (i64 15 to ptr) to i64
  %v78 = ptrtoint ptr inttoptr (i64 1 to ptr) to i64
  %v79 = and i64 %v77, %v78
  %v80 = and i64 %v79, 1
  %v81 = icmp ne i64 %v80, 0
  br i1 %v81, label %yes.82, label %no.83
yes.82:
  %v85 = sub i64 %v78, 1
  %v86 = call { i64, i1 } @llvm.sadd.with.overflow.i64(i64 %v77, i64 %v85)
  %v87 = extractvalue { i64, i1 } %v86, 0
  %v88 = extractvalue { i64, i1 } %v86, 1
  br i1 %v88, label %yes.89, label %no.90
yes.89:
  %v92 = call ptr @mlf_add_int(ptr inttoptr (i64 15 to ptr), ptr inttoptr (i64 1 to ptr))
  br label %join.91
no.90:
  %v93 = inttoptr i64 %v87 to ptr
  br label %join.91
join.91:
  %v94 = phi ptr [ %v92, %yes.89 ], [ %v93, %no.90 ]
  br label %join.84
no.83:
  %v95 = call ptr @mlf_add_int(ptr inttoptr (i64 15 to ptr), ptr inttoptr (i64 1 to ptr))
  br label %join.84
join.84:
  %v96 = phi ptr [ %v94, %join.91 ], [ %v95, %no.83 ]
  ret ptr %v96
}

define private ptr @mlf.code.73(ptr %env, ptr %arg) {
entry:
  %v74 = getelementptr i8, ptr %env, i64 24
  %v75 = load ptr, ptr %v74, align 8, !tbaa !3
  %v97 = call ptr @mlf_thunk(ptr @mlf.code.76, ptr null)
  %v98 = call ptr @mlf_double(double 0x40135da0343cd92c)
  %v99 = call ptr @mlf_prim3(i64 33, ptr %v75, ptr %v97, ptr %v98)
  ret ptr %v99
}

define private ptr @mlf.code.111(ptr %env, ptr %arg) {
entry:
  %v112 = ptrtoint ptr inttoptr (i64 15 to ptr) to i64
  %v113 = ptrtoint ptr inttoptr (i64 3 to ptr) to i64
  %v114 = and i64 %v112, %v113
  %v115 = and i64 %v114, 1
  %v116 = icmp ne i64 %v115, 0
  br i1 %v116, label %yes.117, label %no.118
yes.117:
  %v120 = sub i64 %v113, 1
  %v121 = call { i64, i1 } @llvm.sadd.with.overflow.i64(i64 %v112, i64 %v120)
  %v122 = extractvalue { i64, i1 } %v121, 0
  %v123 = extractvalue { i64, i1 } %v121, 1
  br i1 %v123, label %yes.124, label %no.125
yes.124:
  %v127 = call ptr @mlf_add_int(ptr inttoptr (i64 15 to ptr), ptr inttoptr (i64 3 to ptr))
  br label %join.126
no.125:
  %v128 = inttoptr i64 %v122 to ptr
  br label %join.126
join.126:
  %v129 = phi ptr [ %v127, %yes.124 ], [ %v128, %no.125 ]
  br label %join.119
no.118:
  %v130 = call ptr @mlf_add_int(ptr inttoptr (i64 15 to ptr), ptr inttoptr (i64 3 to ptr))
  br label %join.119
join.119:
  %v131 = phi ptr [ %v129, %join.126 ], [ %v130, %no.118 ]
  ret ptr %v131
}

define private ptr @mlf.code.108(ptr %env, ptr %arg) {
entry:
  %v109 = getelementptr i8, ptr %env, i64 24
  %v110 = load ptr, ptr %v109, align 8, !tbaa !3
  %v132 = call ptr @mlf_thunk(ptr @mlf.code.111, ptr null)
  %v133 = call ptr @mlf_double(double 0xbff290abc01fdb7c)
  %v134 = call ptr @mlf_prim3(i64 33, ptr %v110, ptr %v132, ptr %v133)
  ret ptr %v134
}

define private ptr @mlf.code.146(ptr %env, ptr %arg) {
entry:
  %v147 = ptrtoint ptr inttoptr (i64 15 to ptr) to i64
  %v148 = ptrtoint ptr inttoptr (i64 5 to ptr) to i64
  %v149 = and i64 %v147, %v148
  %v150 = and i64 %v149, 1
  %v151 = icmp ne i64 %v150, 0
  br i1 %v151, label %yes.152, label %no.153
yes.152:
  %v155 = sub i64 %v148, 1
  %v156 = call { i64, i1 } @llvm.sadd.with.overflow.i64(i64 %v147, i64 %v155)
  %v157 = extractvalue { i64, i1 } %v156, 0
  %v158 = extractvalue { i64, i1 } %v156, 1
  br i1 %v158, label %yes.159, label %no.160
yes.159:
  %v162 = call ptr @mlf_add_int(ptr inttoptr (i64 15 to ptr), ptr inttoptr (i64 5 to ptr))
  br label %join.161
no.160:
  %v163 = inttoptr i64 %v157 to ptr
  br label %join.161
join.161:
  %v164 = phi ptr [ %v162, %yes.159 ], [ %v163, %no.160 ]
  br label %join.154
no.153:
  %v165 = call ptr @mlf_add_int(ptr inttoptr (i64 15 to ptr), ptr inttoptr (i64 5 to ptr))
  br label %join.154
join.154:
  %v166 = phi ptr [ %v164, %join.161 ], [ %v165, %no.153 ]
  ret ptr %v166
}

define private ptr @mlf.code.143(ptr %env, ptr %arg) {
entry:
  %v144 = getelementptr i8, ptr %env, i64 24
  %v145 = load ptr, ptr %v144, align 8, !tbaa !3
  %v167 = call ptr @mlf_thunk(ptr @mlf.code.146, ptr null)
  %v168 = call ptr @mlf_double(double 0xbfba86f96c25ebf0)
  %v169 = call ptr @mlf_prim3(i64 33, ptr %v145, ptr %v167, ptr %v168)
  ret ptr %v169
}

define private ptr @mlf.code.181(ptr %env, ptr %arg) {
entry:
  %v182 = call ptr @mlf_double(double 0x3f5b32ddb8ec9209)
  %v183 = call ptr @mlf_double(double 0x4076d3d70a3d70a4)
  %v184 = getelementptr i8, ptr %v182, i64 24
  %v185 = load double, ptr %v184, align 8, !tbaa !3
  %v186 = getelementptr i8, ptr %v183, i64 24
  %v187 = load double, ptr %v186, align 8, !tbaa !3
  %v188 = fmul double %v185, %v187
  %v189 = call ptr @mlf_double(double %v188)
  ret ptr %v189
}

define private ptr @mlf.code.191(ptr %env, ptr %arg) {
entry:
  %v192 = ptrtoint ptr inttoptr (i64 15 to ptr) to i64
  %v193 = ptrtoint ptr inttoptr (i64 7 to ptr) to i64
  %v194 = and i64 %v192, %v193
  %v195 = and i64 %v194, 1
  %v196 = icmp ne i64 %v195, 0
  br i1 %v196, label %yes.197, label %no.198
yes.197:
  %v200 = sub i64 %v193, 1
  %v201 = call { i64, i1 } @llvm.sadd.with.overflow.i64(i64 %v192, i64 %v200)
  %v202 = extractvalue { i64, i1 } %v201, 0
  %v203 = extractvalue { i64, i1 } %v201, 1
  br i1 %v203, label %yes.204, label %no.205
yes.204:
  %v207 = call ptr @mlf_add_int(ptr inttoptr (i64 15 to ptr), ptr inttoptr (i64 7 to ptr))
  br label %join.206
no.205:
  %v208 = inttoptr i64 %v202 to ptr
  br label %join.206
join.206:
  %v209 = phi ptr [ %v207, %yes.204 ], [ %v208, %no.205 ]
  br label %join.199
no.198:
  %v210 = call ptr @mlf_add_int(ptr inttoptr (i64 15 to ptr), ptr inttoptr (i64 7 to ptr))
  br label %join.199
join.199:
  %v211 = phi ptr [ %v209, %join.206 ], [ %v210, %no.198 ]
  ret ptr %v211
}

define private ptr @mlf.code.178(ptr %env, ptr %arg) {
entry:
  %v179 = getelementptr i8, ptr %env, i64 24
  %v180 = load ptr, ptr %v179, align 8, !tbaa !3
  %v190 = call ptr @mlf_thunk(ptr @mlf.code.181, ptr null)
  %v212 = call ptr @mlf_thunk(ptr @mlf.code.191, ptr null)
  %v213 = call ptr @mlf_prim3(i64 33, ptr %v180, ptr %v212, ptr %v190)
  ret ptr %v213
}

define private ptr @mlf.code.225(ptr %env, ptr %arg) {
entry:
  %v226 = call ptr @mlf_double(double 0x3f7f88ff93f670b6)
  %v227 = call ptr @mlf_double(double 0x4076d3d70a3d70a4)
  %v228 = getelementptr i8, ptr %v226, i64 24
  %v229 = load double, ptr %v228, align 8, !tbaa !3
  %v230 = getelementptr i8, ptr %v227, i64 24
  %v231 = load double, ptr %v230, align 8, !tbaa !3
  %v232 = fmul double %v229, %v231
  %v233 = call ptr @mlf_double(double %v232)
  ret ptr %v233
}

define private ptr @mlf.code.235(ptr %env, ptr %arg) {
entry:
  %v236 = ptrtoint ptr inttoptr (i64 15 to ptr) to i64
  %v237 = ptrtoint ptr inttoptr (i64 9 to ptr) to i64
  %v238 = and i64 %v236, %v237
  %v239 = and i64 %v238, 1
  %v240 = icmp ne i64 %v239, 0
  br i1 %v240, label %yes.241, label %no.242
yes.241:
  %v244 = sub i64 %v237, 1
  %v245 = call { i64, i1 } @llvm.sadd.with.overflow.i64(i64 %v236, i64 %v244)
  %v246 = extractvalue { i64, i1 } %v245, 0
  %v247 = extractvalue { i64, i1 } %v245, 1
  br i1 %v247, label %yes.248, label %no.249
yes.248:
  %v251 = call ptr @mlf_add_int(ptr inttoptr (i64 15 to ptr), ptr inttoptr (i64 9 to ptr))
  br label %join.250
no.249:
  %v252 = inttoptr i64 %v246 to ptr
  br label %join.250
join.250:
  %v253 = phi ptr [ %v251, %yes.248 ], [ %v252, %no.249 ]
  br label %join.243
no.242:
  %v254 = call ptr @mlf_add_int(ptr inttoptr (i64 15 to ptr), ptr inttoptr (i64 9 to ptr))
  br label %join.243
join.243:
  %v255 = phi ptr [ %v253, %join.250 ], [ %v254, %no.242 ]
  ret ptr %v255
}

define private ptr @mlf.code.222(ptr %env, ptr %arg) {
entry:
  %v223 = getelementptr i8, ptr %env, i64 24
  %v224 = load ptr, ptr %v223, align 8, !tbaa !3
  %v234 = call ptr @mlf_thunk(ptr @mlf.code.225, ptr null)
  %v256 = call ptr @mlf_thunk(ptr @mlf.code.235, ptr null)
  %v257 = call ptr @mlf_prim3(i64 33, ptr %v224, ptr %v256, ptr %v234)
  ret ptr %v257
}

define private ptr @mlf.code.269(ptr %env, ptr %arg) {
entry:
  %v270 = call ptr @mlf_double(double 0xbf12199946debd80)
  %v271 = call ptr @mlf_double(double 0x4076d3d70a3d70a4)
  %v272 = getelementptr i8, ptr %v270, i64 24
  %v273 = load double, ptr %v272, align 8, !tbaa !3
  %v274 = getelementptr i8, ptr %v271, i64 24
  %v275 = load double, ptr %v274, align 8, !tbaa !3
  %v276 = fmul double %v273, %v275
  %v277 = call ptr @mlf_double(double %v276)
  ret ptr %v277
}

define private ptr @mlf.code.279(ptr %env, ptr %arg) {
entry:
  %v280 = ptrtoint ptr inttoptr (i64 15 to ptr) to i64
  %v281 = ptrtoint ptr inttoptr (i64 11 to ptr) to i64
  %v282 = and i64 %v280, %v281
  %v283 = and i64 %v282, 1
  %v284 = icmp ne i64 %v283, 0
  br i1 %v284, label %yes.285, label %no.286
yes.285:
  %v288 = sub i64 %v281, 1
  %v289 = call { i64, i1 } @llvm.sadd.with.overflow.i64(i64 %v280, i64 %v288)
  %v290 = extractvalue { i64, i1 } %v289, 0
  %v291 = extractvalue { i64, i1 } %v289, 1
  br i1 %v291, label %yes.292, label %no.293
yes.292:
  %v295 = call ptr @mlf_add_int(ptr inttoptr (i64 15 to ptr), ptr inttoptr (i64 11 to ptr))
  br label %join.294
no.293:
  %v296 = inttoptr i64 %v290 to ptr
  br label %join.294
join.294:
  %v297 = phi ptr [ %v295, %yes.292 ], [ %v296, %no.293 ]
  br label %join.287
no.286:
  %v298 = call ptr @mlf_add_int(ptr inttoptr (i64 15 to ptr), ptr inttoptr (i64 11 to ptr))
  br label %join.287
join.287:
  %v299 = phi ptr [ %v297, %join.294 ], [ %v298, %no.286 ]
  ret ptr %v299
}

define private ptr @mlf.code.266(ptr %env, ptr %arg) {
entry:
  %v267 = getelementptr i8, ptr %env, i64 24
  %v268 = load ptr, ptr %v267, align 8, !tbaa !3
  %v278 = call ptr @mlf_thunk(ptr @mlf.code.269, ptr null)
  %v300 = call ptr @mlf_thunk(ptr @mlf.code.279, ptr null)
  %v301 = call ptr @mlf_prim3(i64 33, ptr %v268, ptr %v300, ptr %v278)
  ret ptr %v301
}

define private ptr @mlf.code.315(ptr %env, ptr %arg) {
entry:
  %v316 = getelementptr i8, ptr %env, i64 24
  %v317 = load ptr, ptr %v316, align 8, !tbaa !3
  %v318 = call ptr @mlf_double(double 0x3f4f49601333c135)
  %v319 = call ptr @mlf_force(ptr %v317)
  %v320 = getelementptr i8, ptr %v318, i64 24
  %v321 = load double, ptr %v320, align 8, !tbaa !3
  %v322 = getelementptr i8, ptr %v319, i64 24
  %v323 = load double, ptr %v322, align 8, !tbaa !3
  %v324 = fmul double %v321, %v323
  %v325 = call ptr @mlf_double(double %v324)
  ret ptr %v325
}

define private ptr @mlf.code.329(ptr %env, ptr %arg) {
entry:
  %v330 = ptrtoint ptr inttoptr (i64 15 to ptr) to i64
  %v331 = ptrtoint ptr inttoptr (i64 13 to ptr) to i64
  %v332 = and i64 %v330, %v331
  %v333 = and i64 %v332, 1
  %v334 = icmp ne i64 %v333, 0
  br i1 %v334, label %yes.335, label %no.336
yes.335:
  %v338 = sub i64 %v331, 1
  %v339 = call { i64, i1 } @llvm.sadd.with.overflow.i64(i64 %v330, i64 %v338)
  %v340 = extractvalue { i64, i1 } %v339, 0
  %v341 = extractvalue { i64, i1 } %v339, 1
  br i1 %v341, label %yes.342, label %no.343
yes.342:
  %v345 = call ptr @mlf_add_int(ptr inttoptr (i64 15 to ptr), ptr inttoptr (i64 13 to ptr))
  br label %join.344
no.343:
  %v346 = inttoptr i64 %v340 to ptr
  br label %join.344
join.344:
  %v347 = phi ptr [ %v345, %yes.342 ], [ %v346, %no.343 ]
  br label %join.337
no.336:
  %v348 = call ptr @mlf_add_int(ptr inttoptr (i64 15 to ptr), ptr inttoptr (i64 13 to ptr))
  br label %join.337
join.337:
  %v349 = phi ptr [ %v347, %join.344 ], [ %v348, %no.336 ]
  ret ptr %v349
}

define private ptr @mlf.code.310(ptr %env, ptr %arg) {
entry:
  %v311 = getelementptr i8, ptr %env, i64 24
  %v312 = load ptr, ptr %v311, align 8, !tbaa !3
  %v313 = getelementptr i8, ptr %env, i64 32
  %v314 = load ptr, ptr %v313, align 8, !tbaa !3
  %v326 = call ptr @mlf_env_new(i64 1)
  %v327 = getelementptr i8, ptr %v326, i64 24
  store ptr %v312, ptr %v327, align 8, !tbaa !3
  %v328 = call ptr @mlf_thunk(ptr @mlf.code.315, ptr %v326)
  %v350 = call ptr @mlf_thunk(ptr @mlf.code.329, ptr null)
  %v351 = call ptr @mlf_prim3(i64 33, ptr %v314, ptr %v350, ptr %v328)
  ret ptr %v351
}

define private ptr @mlf.code.364(ptr %env, ptr %arg) {
entry:
  %v365 = ptrtoint ptr inttoptr (i64 29 to ptr) to i64
  %v366 = ptrtoint ptr inttoptr (i64 1 to ptr) to i64
  %v367 = and i64 %v365, %v366
  %v368 = and i64 %v367, 1
  %v369 = icmp ne i64 %v368, 0
  br i1 %v369, label %yes.370, label %no.371
yes.370:
  %v373 = sub i64 %v366, 1
  %v374 = call { i64, i1 } @llvm.sadd.with.overflow.i64(i64 %v365, i64 %v373)
  %v375 = extractvalue { i64, i1 } %v374, 0
  %v376 = extractvalue { i64, i1 } %v374, 1
  br i1 %v376, label %yes.377, label %no.378
yes.377:
  %v380 = call ptr @mlf_add_int(ptr inttoptr (i64 29 to ptr), ptr inttoptr (i64 1 to ptr))
  br label %join.379
no.378:
  %v381 = inttoptr i64 %v375 to ptr
  br label %join.379
join.379:
  %v382 = phi ptr [ %v380, %yes.377 ], [ %v381, %no.378 ]
  br label %join.372
no.371:
  %v383 = call ptr @mlf_add_int(ptr inttoptr (i64 29 to ptr), ptr inttoptr (i64 1 to ptr))
  br label %join.372
join.372:
  %v384 = phi ptr [ %v382, %join.379 ], [ %v383, %no.371 ]
  ret ptr %v384
}

define private ptr @mlf.code.361(ptr %env, ptr %arg) {
entry:
  %v362 = getelementptr i8, ptr %env, i64 24
  %v363 = load ptr, ptr %v362, align 8, !tbaa !3
  %v385 = call ptr @mlf_thunk(ptr @mlf.code.364, ptr null)
  %v386 = call ptr @mlf_double(double 0x4020afcdc332ca67)
  %v387 = call ptr @mlf_prim3(i64 33, ptr %v363, ptr %v385, ptr %v386)
  ret ptr %v387
}

define private ptr @mlf.code.399(ptr %env, ptr %arg) {
entry:
  %v400 = ptrtoint ptr inttoptr (i64 29 to ptr) to i64
  %v401 = ptrtoint ptr inttoptr (i64 3 to ptr) to i64
  %v402 = and i64 %v400, %v401
  %v403 = and i64 %v402, 1
  %v404 = icmp ne i64 %v403, 0
  br i1 %v404, label %yes.405, label %no.406
yes.405:
  %v408 = sub i64 %v401, 1
  %v409 = call { i64, i1 } @llvm.sadd.with.overflow.i64(i64 %v400, i64 %v408)
  %v410 = extractvalue { i64, i1 } %v409, 0
  %v411 = extractvalue { i64, i1 } %v409, 1
  br i1 %v411, label %yes.412, label %no.413
yes.412:
  %v415 = call ptr @mlf_add_int(ptr inttoptr (i64 29 to ptr), ptr inttoptr (i64 3 to ptr))
  br label %join.414
no.413:
  %v416 = inttoptr i64 %v410 to ptr
  br label %join.414
join.414:
  %v417 = phi ptr [ %v415, %yes.412 ], [ %v416, %no.413 ]
  br label %join.407
no.406:
  %v418 = call ptr @mlf_add_int(ptr inttoptr (i64 29 to ptr), ptr inttoptr (i64 3 to ptr))
  br label %join.407
join.407:
  %v419 = phi ptr [ %v417, %join.414 ], [ %v418, %no.406 ]
  ret ptr %v419
}

define private ptr @mlf.code.396(ptr %env, ptr %arg) {
entry:
  %v397 = getelementptr i8, ptr %env, i64 24
  %v398 = load ptr, ptr %v397, align 8, !tbaa !3
  %v420 = call ptr @mlf_thunk(ptr @mlf.code.399, ptr null)
  %v421 = call ptr @mlf_double(double 0x40107fcb31de01b0)
  %v422 = call ptr @mlf_prim3(i64 33, ptr %v398, ptr %v420, ptr %v421)
  ret ptr %v422
}

define private ptr @mlf.code.434(ptr %env, ptr %arg) {
entry:
  %v435 = ptrtoint ptr inttoptr (i64 29 to ptr) to i64
  %v436 = ptrtoint ptr inttoptr (i64 5 to ptr) to i64
  %v437 = and i64 %v435, %v436
  %v438 = and i64 %v437, 1
  %v439 = icmp ne i64 %v438, 0
  br i1 %v439, label %yes.440, label %no.441
yes.440:
  %v443 = sub i64 %v436, 1
  %v444 = call { i64, i1 } @llvm.sadd.with.overflow.i64(i64 %v435, i64 %v443)
  %v445 = extractvalue { i64, i1 } %v444, 0
  %v446 = extractvalue { i64, i1 } %v444, 1
  br i1 %v446, label %yes.447, label %no.448
yes.447:
  %v450 = call ptr @mlf_add_int(ptr inttoptr (i64 29 to ptr), ptr inttoptr (i64 5 to ptr))
  br label %join.449
no.448:
  %v451 = inttoptr i64 %v445 to ptr
  br label %join.449
join.449:
  %v452 = phi ptr [ %v450, %yes.447 ], [ %v451, %no.448 ]
  br label %join.442
no.441:
  %v453 = call ptr @mlf_add_int(ptr inttoptr (i64 29 to ptr), ptr inttoptr (i64 5 to ptr))
  br label %join.442
join.442:
  %v454 = phi ptr [ %v452, %join.449 ], [ %v453, %no.441 ]
  ret ptr %v454
}

define private ptr @mlf.code.431(ptr %env, ptr %arg) {
entry:
  %v432 = getelementptr i8, ptr %env, i64 24
  %v433 = load ptr, ptr %v432, align 8, !tbaa !3
  %v455 = call ptr @mlf_thunk(ptr @mlf.code.434, ptr null)
  %v456 = call ptr @mlf_double(double 0xbfd9d353e1eb467c)
  %v457 = call ptr @mlf_prim3(i64 33, ptr %v433, ptr %v455, ptr %v456)
  ret ptr %v457
}

define private ptr @mlf.code.469(ptr %env, ptr %arg) {
entry:
  %v470 = call ptr @mlf_double(double 0xbf66abb60a8e1d76)
  %v471 = call ptr @mlf_double(double 0x4076d3d70a3d70a4)
  %v472 = getelementptr i8, ptr %v470, i64 24
  %v473 = load double, ptr %v472, align 8, !tbaa !3
  %v474 = getelementptr i8, ptr %v471, i64 24
  %v475 = load double, ptr %v474, align 8, !tbaa !3
  %v476 = fmul double %v473, %v475
  %v477 = call ptr @mlf_double(double %v476)
  ret ptr %v477
}

define private ptr @mlf.code.479(ptr %env, ptr %arg) {
entry:
  %v480 = ptrtoint ptr inttoptr (i64 29 to ptr) to i64
  %v481 = ptrtoint ptr inttoptr (i64 7 to ptr) to i64
  %v482 = and i64 %v480, %v481
  %v483 = and i64 %v482, 1
  %v484 = icmp ne i64 %v483, 0
  br i1 %v484, label %yes.485, label %no.486
yes.485:
  %v488 = sub i64 %v481, 1
  %v489 = call { i64, i1 } @llvm.sadd.with.overflow.i64(i64 %v480, i64 %v488)
  %v490 = extractvalue { i64, i1 } %v489, 0
  %v491 = extractvalue { i64, i1 } %v489, 1
  br i1 %v491, label %yes.492, label %no.493
yes.492:
  %v495 = call ptr @mlf_add_int(ptr inttoptr (i64 29 to ptr), ptr inttoptr (i64 7 to ptr))
  br label %join.494
no.493:
  %v496 = inttoptr i64 %v490 to ptr
  br label %join.494
join.494:
  %v497 = phi ptr [ %v495, %yes.492 ], [ %v496, %no.493 ]
  br label %join.487
no.486:
  %v498 = call ptr @mlf_add_int(ptr inttoptr (i64 29 to ptr), ptr inttoptr (i64 7 to ptr))
  br label %join.487
join.487:
  %v499 = phi ptr [ %v497, %join.494 ], [ %v498, %no.486 ]
  ret ptr %v499
}

define private ptr @mlf.code.466(ptr %env, ptr %arg) {
entry:
  %v467 = getelementptr i8, ptr %env, i64 24
  %v468 = load ptr, ptr %v467, align 8, !tbaa !3
  %v478 = call ptr @mlf_thunk(ptr @mlf.code.469, ptr null)
  %v500 = call ptr @mlf_thunk(ptr @mlf.code.479, ptr null)
  %v501 = call ptr @mlf_prim3(i64 33, ptr %v468, ptr %v500, ptr %v478)
  ret ptr %v501
}

define private ptr @mlf.code.513(ptr %env, ptr %arg) {
entry:
  %v514 = call ptr @mlf_double(double 0x3f747956257578b8)
  %v515 = call ptr @mlf_double(double 0x4076d3d70a3d70a4)
  %v516 = getelementptr i8, ptr %v514, i64 24
  %v517 = load double, ptr %v516, align 8, !tbaa !3
  %v518 = getelementptr i8, ptr %v515, i64 24
  %v519 = load double, ptr %v518, align 8, !tbaa !3
  %v520 = fmul double %v517, %v519
  %v521 = call ptr @mlf_double(double %v520)
  ret ptr %v521
}

define private ptr @mlf.code.523(ptr %env, ptr %arg) {
entry:
  %v524 = ptrtoint ptr inttoptr (i64 29 to ptr) to i64
  %v525 = ptrtoint ptr inttoptr (i64 9 to ptr) to i64
  %v526 = and i64 %v524, %v525
  %v527 = and i64 %v526, 1
  %v528 = icmp ne i64 %v527, 0
  br i1 %v528, label %yes.529, label %no.530
yes.529:
  %v532 = sub i64 %v525, 1
  %v533 = call { i64, i1 } @llvm.sadd.with.overflow.i64(i64 %v524, i64 %v532)
  %v534 = extractvalue { i64, i1 } %v533, 0
  %v535 = extractvalue { i64, i1 } %v533, 1
  br i1 %v535, label %yes.536, label %no.537
yes.536:
  %v539 = call ptr @mlf_add_int(ptr inttoptr (i64 29 to ptr), ptr inttoptr (i64 9 to ptr))
  br label %join.538
no.537:
  %v540 = inttoptr i64 %v534 to ptr
  br label %join.538
join.538:
  %v541 = phi ptr [ %v539, %yes.536 ], [ %v540, %no.537 ]
  br label %join.531
no.530:
  %v542 = call ptr @mlf_add_int(ptr inttoptr (i64 29 to ptr), ptr inttoptr (i64 9 to ptr))
  br label %join.531
join.531:
  %v543 = phi ptr [ %v541, %join.538 ], [ %v542, %no.530 ]
  ret ptr %v543
}

define private ptr @mlf.code.510(ptr %env, ptr %arg) {
entry:
  %v511 = getelementptr i8, ptr %env, i64 24
  %v512 = load ptr, ptr %v511, align 8, !tbaa !3
  %v522 = call ptr @mlf_thunk(ptr @mlf.code.513, ptr null)
  %v544 = call ptr @mlf_thunk(ptr @mlf.code.523, ptr null)
  %v545 = call ptr @mlf_prim3(i64 33, ptr %v512, ptr %v544, ptr %v522)
  ret ptr %v545
}

define private ptr @mlf.code.557(ptr %env, ptr %arg) {
entry:
  %v558 = call ptr @mlf_double(double 0x3ef829379cad4ac0)
  %v559 = call ptr @mlf_double(double 0x4076d3d70a3d70a4)
  %v560 = getelementptr i8, ptr %v558, i64 24
  %v561 = load double, ptr %v560, align 8, !tbaa !3
  %v562 = getelementptr i8, ptr %v559, i64 24
  %v563 = load double, ptr %v562, align 8, !tbaa !3
  %v564 = fmul double %v561, %v563
  %v565 = call ptr @mlf_double(double %v564)
  ret ptr %v565
}

define private ptr @mlf.code.567(ptr %env, ptr %arg) {
entry:
  %v568 = ptrtoint ptr inttoptr (i64 29 to ptr) to i64
  %v569 = ptrtoint ptr inttoptr (i64 11 to ptr) to i64
  %v570 = and i64 %v568, %v569
  %v571 = and i64 %v570, 1
  %v572 = icmp ne i64 %v571, 0
  br i1 %v572, label %yes.573, label %no.574
yes.573:
  %v576 = sub i64 %v569, 1
  %v577 = call { i64, i1 } @llvm.sadd.with.overflow.i64(i64 %v568, i64 %v576)
  %v578 = extractvalue { i64, i1 } %v577, 0
  %v579 = extractvalue { i64, i1 } %v577, 1
  br i1 %v579, label %yes.580, label %no.581
yes.580:
  %v583 = call ptr @mlf_add_int(ptr inttoptr (i64 29 to ptr), ptr inttoptr (i64 11 to ptr))
  br label %join.582
no.581:
  %v584 = inttoptr i64 %v578 to ptr
  br label %join.582
join.582:
  %v585 = phi ptr [ %v583, %yes.580 ], [ %v584, %no.581 ]
  br label %join.575
no.574:
  %v586 = call ptr @mlf_add_int(ptr inttoptr (i64 29 to ptr), ptr inttoptr (i64 11 to ptr))
  br label %join.575
join.575:
  %v587 = phi ptr [ %v585, %join.582 ], [ %v586, %no.574 ]
  ret ptr %v587
}

define private ptr @mlf.code.554(ptr %env, ptr %arg) {
entry:
  %v555 = getelementptr i8, ptr %env, i64 24
  %v556 = load ptr, ptr %v555, align 8, !tbaa !3
  %v566 = call ptr @mlf_thunk(ptr @mlf.code.557, ptr null)
  %v588 = call ptr @mlf_thunk(ptr @mlf.code.567, ptr null)
  %v589 = call ptr @mlf_prim3(i64 33, ptr %v556, ptr %v588, ptr %v566)
  ret ptr %v589
}

define private ptr @mlf.code.603(ptr %env, ptr %arg) {
entry:
  %v604 = getelementptr i8, ptr %env, i64 24
  %v605 = load ptr, ptr %v604, align 8, !tbaa !3
  %v606 = call ptr @mlf_double(double 0x3f32bc5eeff5e6f8)
  %v607 = call ptr @mlf_force(ptr %v605)
  %v608 = getelementptr i8, ptr %v606, i64 24
  %v609 = load double, ptr %v608, align 8, !tbaa !3
  %v610 = getelementptr i8, ptr %v607, i64 24
  %v611 = load double, ptr %v610, align 8, !tbaa !3
  %v612 = fmul double %v609, %v611
  %v613 = call ptr @mlf_double(double %v612)
  ret ptr %v613
}

define private ptr @mlf.code.617(ptr %env, ptr %arg) {
entry:
  %v618 = ptrtoint ptr inttoptr (i64 29 to ptr) to i64
  %v619 = ptrtoint ptr inttoptr (i64 13 to ptr) to i64
  %v620 = and i64 %v618, %v619
  %v621 = and i64 %v620, 1
  %v622 = icmp ne i64 %v621, 0
  br i1 %v622, label %yes.623, label %no.624
yes.623:
  %v626 = sub i64 %v619, 1
  %v627 = call { i64, i1 } @llvm.sadd.with.overflow.i64(i64 %v618, i64 %v626)
  %v628 = extractvalue { i64, i1 } %v627, 0
  %v629 = extractvalue { i64, i1 } %v627, 1
  br i1 %v629, label %yes.630, label %no.631
yes.630:
  %v633 = call ptr @mlf_add_int(ptr inttoptr (i64 29 to ptr), ptr inttoptr (i64 13 to ptr))
  br label %join.632
no.631:
  %v634 = inttoptr i64 %v628 to ptr
  br label %join.632
join.632:
  %v635 = phi ptr [ %v633, %yes.630 ], [ %v634, %no.631 ]
  br label %join.625
no.624:
  %v636 = call ptr @mlf_add_int(ptr inttoptr (i64 29 to ptr), ptr inttoptr (i64 13 to ptr))
  br label %join.625
join.625:
  %v637 = phi ptr [ %v635, %join.632 ], [ %v636, %no.624 ]
  ret ptr %v637
}

define private ptr @mlf.code.598(ptr %env, ptr %arg) {
entry:
  %v599 = getelementptr i8, ptr %env, i64 24
  %v600 = load ptr, ptr %v599, align 8, !tbaa !3
  %v601 = getelementptr i8, ptr %env, i64 32
  %v602 = load ptr, ptr %v601, align 8, !tbaa !3
  %v614 = call ptr @mlf_env_new(i64 1)
  %v615 = getelementptr i8, ptr %v614, i64 24
  store ptr %v600, ptr %v615, align 8, !tbaa !3
  %v616 = call ptr @mlf_thunk(ptr @mlf.code.603, ptr %v614)
  %v638 = call ptr @mlf_thunk(ptr @mlf.code.617, ptr null)
  %v639 = call ptr @mlf_prim3(i64 33, ptr %v602, ptr %v638, ptr %v616)
  ret ptr %v639
}

define private ptr @mlf.code.652(ptr %env, ptr %arg) {
entry:
  %v653 = ptrtoint ptr inttoptr (i64 43 to ptr) to i64
  %v654 = ptrtoint ptr inttoptr (i64 1 to ptr) to i64
  %v655 = and i64 %v653, %v654
  %v656 = and i64 %v655, 1
  %v657 = icmp ne i64 %v656, 0
  br i1 %v657, label %yes.658, label %no.659
yes.658:
  %v661 = sub i64 %v654, 1
  %v662 = call { i64, i1 } @llvm.sadd.with.overflow.i64(i64 %v653, i64 %v661)
  %v663 = extractvalue { i64, i1 } %v662, 0
  %v664 = extractvalue { i64, i1 } %v662, 1
  br i1 %v664, label %yes.665, label %no.666
yes.665:
  %v668 = call ptr @mlf_add_int(ptr inttoptr (i64 43 to ptr), ptr inttoptr (i64 1 to ptr))
  br label %join.667
no.666:
  %v669 = inttoptr i64 %v663 to ptr
  br label %join.667
join.667:
  %v670 = phi ptr [ %v668, %yes.665 ], [ %v669, %no.666 ]
  br label %join.660
no.659:
  %v671 = call ptr @mlf_add_int(ptr inttoptr (i64 43 to ptr), ptr inttoptr (i64 1 to ptr))
  br label %join.660
join.660:
  %v672 = phi ptr [ %v670, %join.667 ], [ %v671, %no.659 ]
  ret ptr %v672
}

define private ptr @mlf.code.649(ptr %env, ptr %arg) {
entry:
  %v650 = getelementptr i8, ptr %env, i64 24
  %v651 = load ptr, ptr %v650, align 8, !tbaa !3
  %v673 = call ptr @mlf_thunk(ptr @mlf.code.652, ptr null)
  %v674 = call ptr @mlf_double(double 0x4029c9eacea7d9cf)
  %v675 = call ptr @mlf_prim3(i64 33, ptr %v651, ptr %v673, ptr %v674)
  ret ptr %v675
}

define private ptr @mlf.code.687(ptr %env, ptr %arg) {
entry:
  %v688 = ptrtoint ptr inttoptr (i64 43 to ptr) to i64
  %v689 = ptrtoint ptr inttoptr (i64 3 to ptr) to i64
  %v690 = and i64 %v688, %v689
  %v691 = and i64 %v690, 1
  %v692 = icmp ne i64 %v691, 0
  br i1 %v692, label %yes.693, label %no.694
yes.693:
  %v696 = sub i64 %v689, 1
  %v697 = call { i64, i1 } @llvm.sadd.with.overflow.i64(i64 %v688, i64 %v696)
  %v698 = extractvalue { i64, i1 } %v697, 0
  %v699 = extractvalue { i64, i1 } %v697, 1
  br i1 %v699, label %yes.700, label %no.701
yes.700:
  %v703 = call ptr @mlf_add_int(ptr inttoptr (i64 43 to ptr), ptr inttoptr (i64 3 to ptr))
  br label %join.702
no.701:
  %v704 = inttoptr i64 %v698 to ptr
  br label %join.702
join.702:
  %v705 = phi ptr [ %v703, %yes.700 ], [ %v704, %no.701 ]
  br label %join.695
no.694:
  %v706 = call ptr @mlf_add_int(ptr inttoptr (i64 43 to ptr), ptr inttoptr (i64 3 to ptr))
  br label %join.695
join.695:
  %v707 = phi ptr [ %v705, %join.702 ], [ %v706, %no.694 ]
  ret ptr %v707
}

define private ptr @mlf.code.684(ptr %env, ptr %arg) {
entry:
  %v685 = getelementptr i8, ptr %env, i64 24
  %v686 = load ptr, ptr %v685, align 8, !tbaa !3
  %v708 = call ptr @mlf_thunk(ptr @mlf.code.687, ptr null)
  %v709 = call ptr @mlf_double(double 0xc02e38e8d626667e)
  %v710 = call ptr @mlf_prim3(i64 33, ptr %v686, ptr %v708, ptr %v709)
  ret ptr %v710
}

define private ptr @mlf.code.722(ptr %env, ptr %arg) {
entry:
  %v723 = ptrtoint ptr inttoptr (i64 43 to ptr) to i64
  %v724 = ptrtoint ptr inttoptr (i64 5 to ptr) to i64
  %v725 = and i64 %v723, %v724
  %v726 = and i64 %v725, 1
  %v727 = icmp ne i64 %v726, 0
  br i1 %v727, label %yes.728, label %no.729
yes.728:
  %v731 = sub i64 %v724, 1
  %v732 = call { i64, i1 } @llvm.sadd.with.overflow.i64(i64 %v723, i64 %v731)
  %v733 = extractvalue { i64, i1 } %v732, 0
  %v734 = extractvalue { i64, i1 } %v732, 1
  br i1 %v734, label %yes.735, label %no.736
yes.735:
  %v738 = call ptr @mlf_add_int(ptr inttoptr (i64 43 to ptr), ptr inttoptr (i64 5 to ptr))
  br label %join.737
no.736:
  %v739 = inttoptr i64 %v733 to ptr
  br label %join.737
join.737:
  %v740 = phi ptr [ %v738, %yes.735 ], [ %v739, %no.736 ]
  br label %join.730
no.729:
  %v741 = call ptr @mlf_add_int(ptr inttoptr (i64 43 to ptr), ptr inttoptr (i64 5 to ptr))
  br label %join.730
join.730:
  %v742 = phi ptr [ %v740, %join.737 ], [ %v741, %no.729 ]
  ret ptr %v742
}

define private ptr @mlf.code.719(ptr %env, ptr %arg) {
entry:
  %v720 = getelementptr i8, ptr %env, i64 24
  %v721 = load ptr, ptr %v720, align 8, !tbaa !3
  %v743 = call ptr @mlf_thunk(ptr @mlf.code.722, ptr null)
  %v744 = call ptr @mlf_double(double 0xbfcc9557be257da0)
  %v745 = call ptr @mlf_prim3(i64 33, ptr %v721, ptr %v743, ptr %v744)
  ret ptr %v745
}

define private ptr @mlf.code.757(ptr %env, ptr %arg) {
entry:
  %v758 = call ptr @mlf_double(double 0x3f6849383e87d954)
  %v759 = call ptr @mlf_double(double 0x4076d3d70a3d70a4)
  %v760 = getelementptr i8, ptr %v758, i64 24
  %v761 = load double, ptr %v760, align 8, !tbaa !3
  %v762 = getelementptr i8, ptr %v759, i64 24
  %v763 = load double, ptr %v762, align 8, !tbaa !3
  %v764 = fmul double %v761, %v763
  %v765 = call ptr @mlf_double(double %v764)
  ret ptr %v765
}

define private ptr @mlf.code.767(ptr %env, ptr %arg) {
entry:
  %v768 = ptrtoint ptr inttoptr (i64 43 to ptr) to i64
  %v769 = ptrtoint ptr inttoptr (i64 7 to ptr) to i64
  %v770 = and i64 %v768, %v769
  %v771 = and i64 %v770, 1
  %v772 = icmp ne i64 %v771, 0
  br i1 %v772, label %yes.773, label %no.774
yes.773:
  %v776 = sub i64 %v769, 1
  %v777 = call { i64, i1 } @llvm.sadd.with.overflow.i64(i64 %v768, i64 %v776)
  %v778 = extractvalue { i64, i1 } %v777, 0
  %v779 = extractvalue { i64, i1 } %v777, 1
  br i1 %v779, label %yes.780, label %no.781
yes.780:
  %v783 = call ptr @mlf_add_int(ptr inttoptr (i64 43 to ptr), ptr inttoptr (i64 7 to ptr))
  br label %join.782
no.781:
  %v784 = inttoptr i64 %v778 to ptr
  br label %join.782
join.782:
  %v785 = phi ptr [ %v783, %yes.780 ], [ %v784, %no.781 ]
  br label %join.775
no.774:
  %v786 = call ptr @mlf_add_int(ptr inttoptr (i64 43 to ptr), ptr inttoptr (i64 7 to ptr))
  br label %join.775
join.775:
  %v787 = phi ptr [ %v785, %join.782 ], [ %v786, %no.774 ]
  ret ptr %v787
}

define private ptr @mlf.code.754(ptr %env, ptr %arg) {
entry:
  %v755 = getelementptr i8, ptr %env, i64 24
  %v756 = load ptr, ptr %v755, align 8, !tbaa !3
  %v766 = call ptr @mlf_thunk(ptr @mlf.code.757, ptr null)
  %v788 = call ptr @mlf_thunk(ptr @mlf.code.767, ptr null)
  %v789 = call ptr @mlf_prim3(i64 33, ptr %v756, ptr %v788, ptr %v766)
  ret ptr %v789
}

define private ptr @mlf.code.801(ptr %env, ptr %arg) {
entry:
  %v802 = call ptr @mlf_double(double 0x3f637c044ac0ace1)
  %v803 = call ptr @mlf_double(double 0x4076d3d70a3d70a4)
  %v804 = getelementptr i8, ptr %v802, i64 24
  %v805 = load double, ptr %v804, align 8, !tbaa !3
  %v806 = getelementptr i8, ptr %v803, i64 24
  %v807 = load double, ptr %v806, align 8, !tbaa !3
  %v808 = fmul double %v805, %v807
  %v809 = call ptr @mlf_double(double %v808)
  ret ptr %v809
}

define private ptr @mlf.code.811(ptr %env, ptr %arg) {
entry:
  %v812 = ptrtoint ptr inttoptr (i64 43 to ptr) to i64
  %v813 = ptrtoint ptr inttoptr (i64 9 to ptr) to i64
  %v814 = and i64 %v812, %v813
  %v815 = and i64 %v814, 1
  %v816 = icmp ne i64 %v815, 0
  br i1 %v816, label %yes.817, label %no.818
yes.817:
  %v820 = sub i64 %v813, 1
  %v821 = call { i64, i1 } @llvm.sadd.with.overflow.i64(i64 %v812, i64 %v820)
  %v822 = extractvalue { i64, i1 } %v821, 0
  %v823 = extractvalue { i64, i1 } %v821, 1
  br i1 %v823, label %yes.824, label %no.825
yes.824:
  %v827 = call ptr @mlf_add_int(ptr inttoptr (i64 43 to ptr), ptr inttoptr (i64 9 to ptr))
  br label %join.826
no.825:
  %v828 = inttoptr i64 %v822 to ptr
  br label %join.826
join.826:
  %v829 = phi ptr [ %v827, %yes.824 ], [ %v828, %no.825 ]
  br label %join.819
no.818:
  %v830 = call ptr @mlf_add_int(ptr inttoptr (i64 43 to ptr), ptr inttoptr (i64 9 to ptr))
  br label %join.819
join.819:
  %v831 = phi ptr [ %v829, %join.826 ], [ %v830, %no.818 ]
  ret ptr %v831
}

define private ptr @mlf.code.798(ptr %env, ptr %arg) {
entry:
  %v799 = getelementptr i8, ptr %env, i64 24
  %v800 = load ptr, ptr %v799, align 8, !tbaa !3
  %v810 = call ptr @mlf_thunk(ptr @mlf.code.801, ptr null)
  %v832 = call ptr @mlf_thunk(ptr @mlf.code.811, ptr null)
  %v833 = call ptr @mlf_prim3(i64 33, ptr %v800, ptr %v832, ptr %v810)
  ret ptr %v833
}

define private ptr @mlf.code.845(ptr %env, ptr %arg) {
entry:
  %v846 = call ptr @mlf_double(double 0xbeff1983fedbfaa0)
  %v847 = call ptr @mlf_double(double 0x4076d3d70a3d70a4)
  %v848 = getelementptr i8, ptr %v846, i64 24
  %v849 = load double, ptr %v848, align 8, !tbaa !3
  %v850 = getelementptr i8, ptr %v847, i64 24
  %v851 = load double, ptr %v850, align 8, !tbaa !3
  %v852 = fmul double %v849, %v851
  %v853 = call ptr @mlf_double(double %v852)
  ret ptr %v853
}

define private ptr @mlf.code.855(ptr %env, ptr %arg) {
entry:
  %v856 = ptrtoint ptr inttoptr (i64 43 to ptr) to i64
  %v857 = ptrtoint ptr inttoptr (i64 11 to ptr) to i64
  %v858 = and i64 %v856, %v857
  %v859 = and i64 %v858, 1
  %v860 = icmp ne i64 %v859, 0
  br i1 %v860, label %yes.861, label %no.862
yes.861:
  %v864 = sub i64 %v857, 1
  %v865 = call { i64, i1 } @llvm.sadd.with.overflow.i64(i64 %v856, i64 %v864)
  %v866 = extractvalue { i64, i1 } %v865, 0
  %v867 = extractvalue { i64, i1 } %v865, 1
  br i1 %v867, label %yes.868, label %no.869
yes.868:
  %v871 = call ptr @mlf_add_int(ptr inttoptr (i64 43 to ptr), ptr inttoptr (i64 11 to ptr))
  br label %join.870
no.869:
  %v872 = inttoptr i64 %v866 to ptr
  br label %join.870
join.870:
  %v873 = phi ptr [ %v871, %yes.868 ], [ %v872, %no.869 ]
  br label %join.863
no.862:
  %v874 = call ptr @mlf_add_int(ptr inttoptr (i64 43 to ptr), ptr inttoptr (i64 11 to ptr))
  br label %join.863
join.863:
  %v875 = phi ptr [ %v873, %join.870 ], [ %v874, %no.862 ]
  ret ptr %v875
}

define private ptr @mlf.code.842(ptr %env, ptr %arg) {
entry:
  %v843 = getelementptr i8, ptr %env, i64 24
  %v844 = load ptr, ptr %v843, align 8, !tbaa !3
  %v854 = call ptr @mlf_thunk(ptr @mlf.code.845, ptr null)
  %v876 = call ptr @mlf_thunk(ptr @mlf.code.855, ptr null)
  %v877 = call ptr @mlf_prim3(i64 33, ptr %v844, ptr %v876, ptr %v854)
  ret ptr %v877
}

define private ptr @mlf.code.891(ptr %env, ptr %arg) {
entry:
  %v892 = getelementptr i8, ptr %env, i64 24
  %v893 = load ptr, ptr %v892, align 8, !tbaa !3
  %v894 = call ptr @mlf_double(double 0x3f06e44607a13bd6)
  %v895 = call ptr @mlf_force(ptr %v893)
  %v896 = getelementptr i8, ptr %v894, i64 24
  %v897 = load double, ptr %v896, align 8, !tbaa !3
  %v898 = getelementptr i8, ptr %v895, i64 24
  %v899 = load double, ptr %v898, align 8, !tbaa !3
  %v900 = fmul double %v897, %v899
  %v901 = call ptr @mlf_double(double %v900)
  ret ptr %v901
}

define private ptr @mlf.code.905(ptr %env, ptr %arg) {
entry:
  %v906 = ptrtoint ptr inttoptr (i64 43 to ptr) to i64
  %v907 = ptrtoint ptr inttoptr (i64 13 to ptr) to i64
  %v908 = and i64 %v906, %v907
  %v909 = and i64 %v908, 1
  %v910 = icmp ne i64 %v909, 0
  br i1 %v910, label %yes.911, label %no.912
yes.911:
  %v914 = sub i64 %v907, 1
  %v915 = call { i64, i1 } @llvm.sadd.with.overflow.i64(i64 %v906, i64 %v914)
  %v916 = extractvalue { i64, i1 } %v915, 0
  %v917 = extractvalue { i64, i1 } %v915, 1
  br i1 %v917, label %yes.918, label %no.919
yes.918:
  %v921 = call ptr @mlf_add_int(ptr inttoptr (i64 43 to ptr), ptr inttoptr (i64 13 to ptr))
  br label %join.920
no.919:
  %v922 = inttoptr i64 %v916 to ptr
  br label %join.920
join.920:
  %v923 = phi ptr [ %v921, %yes.918 ], [ %v922, %no.919 ]
  br label %join.913
no.912:
  %v924 = call ptr @mlf_add_int(ptr inttoptr (i64 43 to ptr), ptr inttoptr (i64 13 to ptr))
  br label %join.913
join.913:
  %v925 = phi ptr [ %v923, %join.920 ], [ %v924, %no.912 ]
  ret ptr %v925
}

define private ptr @mlf.code.886(ptr %env, ptr %arg) {
entry:
  %v887 = getelementptr i8, ptr %env, i64 24
  %v888 = load ptr, ptr %v887, align 8, !tbaa !3
  %v889 = getelementptr i8, ptr %env, i64 32
  %v890 = load ptr, ptr %v889, align 8, !tbaa !3
  %v902 = call ptr @mlf_env_new(i64 1)
  %v903 = getelementptr i8, ptr %v902, i64 24
  store ptr %v888, ptr %v903, align 8, !tbaa !3
  %v904 = call ptr @mlf_thunk(ptr @mlf.code.891, ptr %v902)
  %v926 = call ptr @mlf_thunk(ptr @mlf.code.905, ptr null)
  %v927 = call ptr @mlf_prim3(i64 33, ptr %v890, ptr %v926, ptr %v904)
  ret ptr %v927
}

define private ptr @mlf.code.940(ptr %env, ptr %arg) {
entry:
  %v941 = ptrtoint ptr inttoptr (i64 57 to ptr) to i64
  %v942 = ptrtoint ptr inttoptr (i64 1 to ptr) to i64
  %v943 = and i64 %v941, %v942
  %v944 = and i64 %v943, 1
  %v945 = icmp ne i64 %v944, 0
  br i1 %v945, label %yes.946, label %no.947
yes.946:
  %v949 = sub i64 %v942, 1
  %v950 = call { i64, i1 } @llvm.sadd.with.overflow.i64(i64 %v941, i64 %v949)
  %v951 = extractvalue { i64, i1 } %v950, 0
  %v952 = extractvalue { i64, i1 } %v950, 1
  br i1 %v952, label %yes.953, label %no.954
yes.953:
  %v956 = call ptr @mlf_add_int(ptr inttoptr (i64 57 to ptr), ptr inttoptr (i64 1 to ptr))
  br label %join.955
no.954:
  %v957 = inttoptr i64 %v951 to ptr
  br label %join.955
join.955:
  %v958 = phi ptr [ %v956, %yes.953 ], [ %v957, %no.954 ]
  br label %join.948
no.947:
  %v959 = call ptr @mlf_add_int(ptr inttoptr (i64 57 to ptr), ptr inttoptr (i64 1 to ptr))
  br label %join.948
join.948:
  %v960 = phi ptr [ %v958, %join.955 ], [ %v959, %no.947 ]
  ret ptr %v960
}

define private ptr @mlf.code.937(ptr %env, ptr %arg) {
entry:
  %v938 = getelementptr i8, ptr %env, i64 24
  %v939 = load ptr, ptr %v938, align 8, !tbaa !3
  %v961 = call ptr @mlf_thunk(ptr @mlf.code.940, ptr null)
  %v962 = call ptr @mlf_double(double 0x402ec267a905572a)
  %v963 = call ptr @mlf_prim3(i64 33, ptr %v939, ptr %v961, ptr %v962)
  ret ptr %v963
}

define private ptr @mlf.code.975(ptr %env, ptr %arg) {
entry:
  %v976 = ptrtoint ptr inttoptr (i64 57 to ptr) to i64
  %v977 = ptrtoint ptr inttoptr (i64 3 to ptr) to i64
  %v978 = and i64 %v976, %v977
  %v979 = and i64 %v978, 1
  %v980 = icmp ne i64 %v979, 0
  br i1 %v980, label %yes.981, label %no.982
yes.981:
  %v984 = sub i64 %v977, 1
  %v985 = call { i64, i1 } @llvm.sadd.with.overflow.i64(i64 %v976, i64 %v984)
  %v986 = extractvalue { i64, i1 } %v985, 0
  %v987 = extractvalue { i64, i1 } %v985, 1
  br i1 %v987, label %yes.988, label %no.989
yes.988:
  %v991 = call ptr @mlf_add_int(ptr inttoptr (i64 57 to ptr), ptr inttoptr (i64 3 to ptr))
  br label %join.990
no.989:
  %v992 = inttoptr i64 %v986 to ptr
  br label %join.990
join.990:
  %v993 = phi ptr [ %v991, %yes.988 ], [ %v992, %no.989 ]
  br label %join.983
no.982:
  %v994 = call ptr @mlf_add_int(ptr inttoptr (i64 57 to ptr), ptr inttoptr (i64 3 to ptr))
  br label %join.983
join.983:
  %v995 = phi ptr [ %v993, %join.990 ], [ %v994, %no.982 ]
  ret ptr %v995
}

define private ptr @mlf.code.972(ptr %env, ptr %arg) {
entry:
  %v973 = getelementptr i8, ptr %env, i64 24
  %v974 = load ptr, ptr %v973, align 8, !tbaa !3
  %v996 = call ptr @mlf_thunk(ptr @mlf.code.975, ptr null)
  %v997 = call ptr @mlf_double(double 0xc039eb5833c8a220)
  %v998 = call ptr @mlf_prim3(i64 33, ptr %v974, ptr %v996, ptr %v997)
  ret ptr %v998
}

define private ptr @mlf.code.1010(ptr %env, ptr %arg) {
entry:
  %v1011 = ptrtoint ptr inttoptr (i64 57 to ptr) to i64
  %v1012 = ptrtoint ptr inttoptr (i64 5 to ptr) to i64
  %v1013 = and i64 %v1011, %v1012
  %v1014 = and i64 %v1013, 1
  %v1015 = icmp ne i64 %v1014, 0
  br i1 %v1015, label %yes.1016, label %no.1017
yes.1016:
  %v1019 = sub i64 %v1012, 1
  %v1020 = call { i64, i1 } @llvm.sadd.with.overflow.i64(i64 %v1011, i64 %v1019)
  %v1021 = extractvalue { i64, i1 } %v1020, 0
  %v1022 = extractvalue { i64, i1 } %v1020, 1
  br i1 %v1022, label %yes.1023, label %no.1024
yes.1023:
  %v1026 = call ptr @mlf_add_int(ptr inttoptr (i64 57 to ptr), ptr inttoptr (i64 5 to ptr))
  br label %join.1025
no.1024:
  %v1027 = inttoptr i64 %v1021 to ptr
  br label %join.1025
join.1025:
  %v1028 = phi ptr [ %v1026, %yes.1023 ], [ %v1027, %no.1024 ]
  br label %join.1018
no.1017:
  %v1029 = call ptr @mlf_add_int(ptr inttoptr (i64 57 to ptr), ptr inttoptr (i64 5 to ptr))
  br label %join.1018
join.1018:
  %v1030 = phi ptr [ %v1028, %join.1025 ], [ %v1029, %no.1017 ]
  ret ptr %v1030
}

define private ptr @mlf.code.1007(ptr %env, ptr %arg) {
entry:
  %v1008 = getelementptr i8, ptr %env, i64 24
  %v1009 = load ptr, ptr %v1008, align 8, !tbaa !3
  %v1031 = call ptr @mlf_thunk(ptr @mlf.code.1010, ptr null)
  %v1032 = call ptr @mlf_double(double 0x3fc6f1f393abe540)
  %v1033 = call ptr @mlf_prim3(i64 33, ptr %v1009, ptr %v1031, ptr %v1032)
  ret ptr %v1033
}

define private ptr @mlf.code.1045(ptr %env, ptr %arg) {
entry:
  %v1046 = call ptr @mlf_double(double 0x3f65f5c9e51b4320)
  %v1047 = call ptr @mlf_double(double 0x4076d3d70a3d70a4)
  %v1048 = getelementptr i8, ptr %v1046, i64 24
  %v1049 = load double, ptr %v1048, align 8, !tbaa !3
  %v1050 = getelementptr i8, ptr %v1047, i64 24
  %v1051 = load double, ptr %v1050, align 8, !tbaa !3
  %v1052 = fmul double %v1049, %v1051
  %v1053 = call ptr @mlf_double(double %v1052)
  ret ptr %v1053
}

define private ptr @mlf.code.1055(ptr %env, ptr %arg) {
entry:
  %v1056 = ptrtoint ptr inttoptr (i64 57 to ptr) to i64
  %v1057 = ptrtoint ptr inttoptr (i64 7 to ptr) to i64
  %v1058 = and i64 %v1056, %v1057
  %v1059 = and i64 %v1058, 1
  %v1060 = icmp ne i64 %v1059, 0
  br i1 %v1060, label %yes.1061, label %no.1062
yes.1061:
  %v1064 = sub i64 %v1057, 1
  %v1065 = call { i64, i1 } @llvm.sadd.with.overflow.i64(i64 %v1056, i64 %v1064)
  %v1066 = extractvalue { i64, i1 } %v1065, 0
  %v1067 = extractvalue { i64, i1 } %v1065, 1
  br i1 %v1067, label %yes.1068, label %no.1069
yes.1068:
  %v1071 = call ptr @mlf_add_int(ptr inttoptr (i64 57 to ptr), ptr inttoptr (i64 7 to ptr))
  br label %join.1070
no.1069:
  %v1072 = inttoptr i64 %v1066 to ptr
  br label %join.1070
join.1070:
  %v1073 = phi ptr [ %v1071, %yes.1068 ], [ %v1072, %no.1069 ]
  br label %join.1063
no.1062:
  %v1074 = call ptr @mlf_add_int(ptr inttoptr (i64 57 to ptr), ptr inttoptr (i64 7 to ptr))
  br label %join.1063
join.1063:
  %v1075 = phi ptr [ %v1073, %join.1070 ], [ %v1074, %no.1062 ]
  ret ptr %v1075
}

define private ptr @mlf.code.1042(ptr %env, ptr %arg) {
entry:
  %v1043 = getelementptr i8, ptr %env, i64 24
  %v1044 = load ptr, ptr %v1043, align 8, !tbaa !3
  %v1054 = call ptr @mlf_thunk(ptr @mlf.code.1045, ptr null)
  %v1076 = call ptr @mlf_thunk(ptr @mlf.code.1055, ptr null)
  %v1077 = call ptr @mlf_prim3(i64 33, ptr %v1044, ptr %v1076, ptr %v1054)
  ret ptr %v1077
}

define private ptr @mlf.code.1089(ptr %env, ptr %arg) {
entry:
  %v1090 = call ptr @mlf_double(double 0x3f5aad5736999d88)
  %v1091 = call ptr @mlf_double(double 0x4076d3d70a3d70a4)
  %v1092 = getelementptr i8, ptr %v1090, i64 24
  %v1093 = load double, ptr %v1092, align 8, !tbaa !3
  %v1094 = getelementptr i8, ptr %v1091, i64 24
  %v1095 = load double, ptr %v1094, align 8, !tbaa !3
  %v1096 = fmul double %v1093, %v1095
  %v1097 = call ptr @mlf_double(double %v1096)
  ret ptr %v1097
}

define private ptr @mlf.code.1099(ptr %env, ptr %arg) {
entry:
  %v1100 = ptrtoint ptr inttoptr (i64 57 to ptr) to i64
  %v1101 = ptrtoint ptr inttoptr (i64 9 to ptr) to i64
  %v1102 = and i64 %v1100, %v1101
  %v1103 = and i64 %v1102, 1
  %v1104 = icmp ne i64 %v1103, 0
  br i1 %v1104, label %yes.1105, label %no.1106
yes.1105:
  %v1108 = sub i64 %v1101, 1
  %v1109 = call { i64, i1 } @llvm.sadd.with.overflow.i64(i64 %v1100, i64 %v1108)
  %v1110 = extractvalue { i64, i1 } %v1109, 0
  %v1111 = extractvalue { i64, i1 } %v1109, 1
  br i1 %v1111, label %yes.1112, label %no.1113
yes.1112:
  %v1115 = call ptr @mlf_add_int(ptr inttoptr (i64 57 to ptr), ptr inttoptr (i64 9 to ptr))
  br label %join.1114
no.1113:
  %v1116 = inttoptr i64 %v1110 to ptr
  br label %join.1114
join.1114:
  %v1117 = phi ptr [ %v1115, %yes.1112 ], [ %v1116, %no.1113 ]
  br label %join.1107
no.1106:
  %v1118 = call ptr @mlf_add_int(ptr inttoptr (i64 57 to ptr), ptr inttoptr (i64 9 to ptr))
  br label %join.1107
join.1107:
  %v1119 = phi ptr [ %v1117, %join.1114 ], [ %v1118, %no.1106 ]
  ret ptr %v1119
}

define private ptr @mlf.code.1086(ptr %env, ptr %arg) {
entry:
  %v1087 = getelementptr i8, ptr %env, i64 24
  %v1088 = load ptr, ptr %v1087, align 8, !tbaa !3
  %v1098 = call ptr @mlf_thunk(ptr @mlf.code.1089, ptr null)
  %v1120 = call ptr @mlf_thunk(ptr @mlf.code.1099, ptr null)
  %v1121 = call ptr @mlf_prim3(i64 33, ptr %v1088, ptr %v1120, ptr %v1098)
  ret ptr %v1121
}

define private ptr @mlf.code.1133(ptr %env, ptr %arg) {
entry:
  %v1134 = call ptr @mlf_double(double 0xbf18f2070b7f9750)
  %v1135 = call ptr @mlf_double(double 0x4076d3d70a3d70a4)
  %v1136 = getelementptr i8, ptr %v1134, i64 24
  %v1137 = load double, ptr %v1136, align 8, !tbaa !3
  %v1138 = getelementptr i8, ptr %v1135, i64 24
  %v1139 = load double, ptr %v1138, align 8, !tbaa !3
  %v1140 = fmul double %v1137, %v1139
  %v1141 = call ptr @mlf_double(double %v1140)
  ret ptr %v1141
}

define private ptr @mlf.code.1143(ptr %env, ptr %arg) {
entry:
  %v1144 = ptrtoint ptr inttoptr (i64 57 to ptr) to i64
  %v1145 = ptrtoint ptr inttoptr (i64 11 to ptr) to i64
  %v1146 = and i64 %v1144, %v1145
  %v1147 = and i64 %v1146, 1
  %v1148 = icmp ne i64 %v1147, 0
  br i1 %v1148, label %yes.1149, label %no.1150
yes.1149:
  %v1152 = sub i64 %v1145, 1
  %v1153 = call { i64, i1 } @llvm.sadd.with.overflow.i64(i64 %v1144, i64 %v1152)
  %v1154 = extractvalue { i64, i1 } %v1153, 0
  %v1155 = extractvalue { i64, i1 } %v1153, 1
  br i1 %v1155, label %yes.1156, label %no.1157
yes.1156:
  %v1159 = call ptr @mlf_add_int(ptr inttoptr (i64 57 to ptr), ptr inttoptr (i64 11 to ptr))
  br label %join.1158
no.1157:
  %v1160 = inttoptr i64 %v1154 to ptr
  br label %join.1158
join.1158:
  %v1161 = phi ptr [ %v1159, %yes.1156 ], [ %v1160, %no.1157 ]
  br label %join.1151
no.1150:
  %v1162 = call ptr @mlf_add_int(ptr inttoptr (i64 57 to ptr), ptr inttoptr (i64 11 to ptr))
  br label %join.1151
join.1151:
  %v1163 = phi ptr [ %v1161, %join.1158 ], [ %v1162, %no.1150 ]
  ret ptr %v1163
}

define private ptr @mlf.code.1130(ptr %env, ptr %arg) {
entry:
  %v1131 = getelementptr i8, ptr %env, i64 24
  %v1132 = load ptr, ptr %v1131, align 8, !tbaa !3
  %v1142 = call ptr @mlf_thunk(ptr @mlf.code.1133, ptr null)
  %v1164 = call ptr @mlf_thunk(ptr @mlf.code.1143, ptr null)
  %v1165 = call ptr @mlf_prim3(i64 33, ptr %v1132, ptr %v1164, ptr %v1142)
  ret ptr %v1165
}

define private ptr @mlf.code.1174(ptr %env, ptr %arg) {
entry:
  %v1175 = getelementptr i8, ptr %env, i64 24
  %v1176 = load ptr, ptr %v1175, align 8, !tbaa !3
  %v1177 = call ptr @mlf_double(double 0x3f0b0213ca2d0eec)
  %v1178 = call ptr @mlf_force(ptr %v1176)
  %v1179 = getelementptr i8, ptr %v1177, i64 24
  %v1180 = load double, ptr %v1179, align 8, !tbaa !3
  %v1181 = getelementptr i8, ptr %v1178, i64 24
  %v1182 = load double, ptr %v1181, align 8, !tbaa !3
  %v1183 = fmul double %v1180, %v1182
  %v1184 = call ptr @mlf_double(double %v1183)
  ret ptr %v1184
}

define private ptr @mlf.code.1188(ptr %env, ptr %arg) {
entry:
  %v1189 = ptrtoint ptr inttoptr (i64 57 to ptr) to i64
  %v1190 = ptrtoint ptr inttoptr (i64 13 to ptr) to i64
  %v1191 = and i64 %v1189, %v1190
  %v1192 = and i64 %v1191, 1
  %v1193 = icmp ne i64 %v1192, 0
  br i1 %v1193, label %yes.1194, label %no.1195
yes.1194:
  %v1197 = sub i64 %v1190, 1
  %v1198 = call { i64, i1 } @llvm.sadd.with.overflow.i64(i64 %v1189, i64 %v1197)
  %v1199 = extractvalue { i64, i1 } %v1198, 0
  %v1200 = extractvalue { i64, i1 } %v1198, 1
  br i1 %v1200, label %yes.1201, label %no.1202
yes.1201:
  %v1204 = call ptr @mlf_add_int(ptr inttoptr (i64 57 to ptr), ptr inttoptr (i64 13 to ptr))
  br label %join.1203
no.1202:
  %v1205 = inttoptr i64 %v1199 to ptr
  br label %join.1203
join.1203:
  %v1206 = phi ptr [ %v1204, %yes.1201 ], [ %v1205, %no.1202 ]
  br label %join.1196
no.1195:
  %v1207 = call ptr @mlf_add_int(ptr inttoptr (i64 57 to ptr), ptr inttoptr (i64 13 to ptr))
  br label %join.1196
join.1196:
  %v1208 = phi ptr [ %v1206, %join.1203 ], [ %v1207, %no.1195 ]
  ret ptr %v1208
}

define private ptr @mlf.code.1169(ptr %env, ptr %arg) {
entry:
  %v1170 = getelementptr i8, ptr %env, i64 24
  %v1171 = load ptr, ptr %v1170, align 8, !tbaa !3
  %v1172 = getelementptr i8, ptr %env, i64 32
  %v1173 = load ptr, ptr %v1172, align 8, !tbaa !3
  %v1185 = call ptr @mlf_env_new(i64 1)
  %v1186 = getelementptr i8, ptr %v1185, i64 24
  store ptr %v1171, ptr %v1186, align 8, !tbaa !3
  %v1187 = call ptr @mlf_thunk(ptr @mlf.code.1174, ptr %v1185)
  %v1209 = call ptr @mlf_thunk(ptr @mlf.code.1188, ptr null)
  %v1210 = call ptr @mlf_prim3(i64 33, ptr %v1173, ptr %v1209, ptr %v1187)
  ret ptr %v1210
}

define private ptr @mlf.code.1125(ptr %env, ptr %arg) {
entry:
  %v1126 = getelementptr i8, ptr %env, i64 24
  %v1127 = load ptr, ptr %v1126, align 8, !tbaa !3
  %v1128 = getelementptr i8, ptr %env, i64 32
  %v1129 = load ptr, ptr %v1128, align 8, !tbaa !3
  %v1166 = call ptr @mlf_env_new(i64 1)
  %v1167 = getelementptr i8, ptr %v1166, i64 24
  store ptr %v1129, ptr %v1167, align 8, !tbaa !3
  %v1168 = call ptr @mlf_thunk(ptr @mlf.code.1130, ptr %v1166)
  %v1211 = call ptr @mlf_env_new(i64 2)
  %v1212 = getelementptr i8, ptr %v1211, i64 24
  store ptr %v1127, ptr %v1212, align 8, !tbaa !3
  %v1213 = getelementptr i8, ptr %v1211, i64 32
  store ptr %v1129, ptr %v1213, align 8, !tbaa !3
  %v1214 = call ptr @mlf_closure(ptr @mlf.code.1169, ptr %v1211)
  %v1215 = call ptr @mlf_prim2(i64 1, ptr %v1168, ptr %v1214)
  ret ptr %v1215
}

define private ptr @mlf.code.1081(ptr %env, ptr %arg) {
entry:
  %v1082 = getelementptr i8, ptr %env, i64 24
  %v1083 = load ptr, ptr %v1082, align 8, !tbaa !3
  %v1084 = getelementptr i8, ptr %env, i64 32
  %v1085 = load ptr, ptr %v1084, align 8, !tbaa !3
  %v1122 = call ptr @mlf_env_new(i64 1)
  %v1123 = getelementptr i8, ptr %v1122, i64 24
  store ptr %v1085, ptr %v1123, align 8, !tbaa !3
  %v1124 = call ptr @mlf_thunk(ptr @mlf.code.1086, ptr %v1122)
  %v1216 = call ptr @mlf_env_new(i64 2)
  %v1217 = getelementptr i8, ptr %v1216, i64 24
  store ptr %v1083, ptr %v1217, align 8, !tbaa !3
  %v1218 = getelementptr i8, ptr %v1216, i64 32
  store ptr %v1085, ptr %v1218, align 8, !tbaa !3
  %v1219 = call ptr @mlf_closure(ptr @mlf.code.1125, ptr %v1216)
  %v1220 = call ptr @mlf_prim2(i64 1, ptr %v1124, ptr %v1219)
  ret ptr %v1220
}

define private ptr @mlf.code.1037(ptr %env, ptr %arg) {
entry:
  %v1038 = getelementptr i8, ptr %env, i64 24
  %v1039 = load ptr, ptr %v1038, align 8, !tbaa !3
  %v1040 = getelementptr i8, ptr %env, i64 32
  %v1041 = load ptr, ptr %v1040, align 8, !tbaa !3
  %v1078 = call ptr @mlf_env_new(i64 1)
  %v1079 = getelementptr i8, ptr %v1078, i64 24
  store ptr %v1041, ptr %v1079, align 8, !tbaa !3
  %v1080 = call ptr @mlf_thunk(ptr @mlf.code.1042, ptr %v1078)
  %v1221 = call ptr @mlf_env_new(i64 2)
  %v1222 = getelementptr i8, ptr %v1221, i64 24
  store ptr %v1039, ptr %v1222, align 8, !tbaa !3
  %v1223 = getelementptr i8, ptr %v1221, i64 32
  store ptr %v1041, ptr %v1223, align 8, !tbaa !3
  %v1224 = call ptr @mlf_closure(ptr @mlf.code.1081, ptr %v1221)
  %v1225 = call ptr @mlf_prim2(i64 1, ptr %v1080, ptr %v1224)
  ret ptr %v1225
}

define private ptr @mlf.code.1002(ptr %env, ptr %arg) {
entry:
  %v1003 = getelementptr i8, ptr %env, i64 24
  %v1004 = load ptr, ptr %v1003, align 8, !tbaa !3
  %v1005 = getelementptr i8, ptr %env, i64 32
  %v1006 = load ptr, ptr %v1005, align 8, !tbaa !3
  %v1034 = call ptr @mlf_env_new(i64 1)
  %v1035 = getelementptr i8, ptr %v1034, i64 24
  store ptr %v1006, ptr %v1035, align 8, !tbaa !3
  %v1036 = call ptr @mlf_thunk(ptr @mlf.code.1007, ptr %v1034)
  %v1226 = call ptr @mlf_env_new(i64 2)
  %v1227 = getelementptr i8, ptr %v1226, i64 24
  store ptr %v1004, ptr %v1227, align 8, !tbaa !3
  %v1228 = getelementptr i8, ptr %v1226, i64 32
  store ptr %v1006, ptr %v1228, align 8, !tbaa !3
  %v1229 = call ptr @mlf_closure(ptr @mlf.code.1037, ptr %v1226)
  %v1230 = call ptr @mlf_prim2(i64 1, ptr %v1036, ptr %v1229)
  ret ptr %v1230
}

define private ptr @mlf.code.967(ptr %env, ptr %arg) {
entry:
  %v968 = getelementptr i8, ptr %env, i64 24
  %v969 = load ptr, ptr %v968, align 8, !tbaa !3
  %v970 = getelementptr i8, ptr %env, i64 32
  %v971 = load ptr, ptr %v970, align 8, !tbaa !3
  %v999 = call ptr @mlf_env_new(i64 1)
  %v1000 = getelementptr i8, ptr %v999, i64 24
  store ptr %v971, ptr %v1000, align 8, !tbaa !3
  %v1001 = call ptr @mlf_thunk(ptr @mlf.code.972, ptr %v999)
  %v1231 = call ptr @mlf_env_new(i64 2)
  %v1232 = getelementptr i8, ptr %v1231, i64 24
  store ptr %v969, ptr %v1232, align 8, !tbaa !3
  %v1233 = getelementptr i8, ptr %v1231, i64 32
  store ptr %v971, ptr %v1233, align 8, !tbaa !3
  %v1234 = call ptr @mlf_closure(ptr @mlf.code.1002, ptr %v1231)
  %v1235 = call ptr @mlf_prim2(i64 1, ptr %v1001, ptr %v1234)
  ret ptr %v1235
}

define private ptr @mlf.code.932(ptr %env, ptr %arg) {
entry:
  %v933 = getelementptr i8, ptr %env, i64 24
  %v934 = load ptr, ptr %v933, align 8, !tbaa !3
  %v935 = getelementptr i8, ptr %env, i64 32
  %v936 = load ptr, ptr %v935, align 8, !tbaa !3
  %v964 = call ptr @mlf_env_new(i64 1)
  %v965 = getelementptr i8, ptr %v964, i64 24
  store ptr %v936, ptr %v965, align 8, !tbaa !3
  %v966 = call ptr @mlf_thunk(ptr @mlf.code.937, ptr %v964)
  %v1236 = call ptr @mlf_env_new(i64 2)
  %v1237 = getelementptr i8, ptr %v1236, i64 24
  store ptr %v934, ptr %v1237, align 8, !tbaa !3
  %v1238 = getelementptr i8, ptr %v1236, i64 32
  store ptr %v936, ptr %v1238, align 8, !tbaa !3
  %v1239 = call ptr @mlf_closure(ptr @mlf.code.967, ptr %v1236)
  %v1240 = call ptr @mlf_prim2(i64 1, ptr %v966, ptr %v1239)
  ret ptr %v1240
}

define private ptr @mlf.code.881(ptr %env, ptr %arg) {
entry:
  %v882 = getelementptr i8, ptr %env, i64 24
  %v883 = load ptr, ptr %v882, align 8, !tbaa !3
  %v884 = getelementptr i8, ptr %env, i64 32
  %v885 = load ptr, ptr %v884, align 8, !tbaa !3
  %v928 = call ptr @mlf_env_new(i64 2)
  %v929 = getelementptr i8, ptr %v928, i64 24
  store ptr %v883, ptr %v929, align 8, !tbaa !3
  %v930 = getelementptr i8, ptr %v928, i64 32
  store ptr %v885, ptr %v930, align 8, !tbaa !3
  %v931 = call ptr @mlf_thunk(ptr @mlf.code.886, ptr %v928)
  %v1241 = call ptr @mlf_env_new(i64 2)
  %v1242 = getelementptr i8, ptr %v1241, i64 24
  store ptr %v883, ptr %v1242, align 8, !tbaa !3
  %v1243 = getelementptr i8, ptr %v1241, i64 32
  store ptr %v885, ptr %v1243, align 8, !tbaa !3
  %v1244 = call ptr @mlf_closure(ptr @mlf.code.932, ptr %v1241)
  %v1245 = call ptr @mlf_prim2(i64 1, ptr %v931, ptr %v1244)
  ret ptr %v1245
}

define private ptr @mlf.code.837(ptr %env, ptr %arg) {
entry:
  %v838 = getelementptr i8, ptr %env, i64 24
  %v839 = load ptr, ptr %v838, align 8, !tbaa !3
  %v840 = getelementptr i8, ptr %env, i64 32
  %v841 = load ptr, ptr %v840, align 8, !tbaa !3
  %v878 = call ptr @mlf_env_new(i64 1)
  %v879 = getelementptr i8, ptr %v878, i64 24
  store ptr %v841, ptr %v879, align 8, !tbaa !3
  %v880 = call ptr @mlf_thunk(ptr @mlf.code.842, ptr %v878)
  %v1246 = call ptr @mlf_env_new(i64 2)
  %v1247 = getelementptr i8, ptr %v1246, i64 24
  store ptr %v839, ptr %v1247, align 8, !tbaa !3
  %v1248 = getelementptr i8, ptr %v1246, i64 32
  store ptr %v841, ptr %v1248, align 8, !tbaa !3
  %v1249 = call ptr @mlf_closure(ptr @mlf.code.881, ptr %v1246)
  %v1250 = call ptr @mlf_prim2(i64 1, ptr %v880, ptr %v1249)
  ret ptr %v1250
}

define private ptr @mlf.code.793(ptr %env, ptr %arg) {
entry:
  %v794 = getelementptr i8, ptr %env, i64 24
  %v795 = load ptr, ptr %v794, align 8, !tbaa !3
  %v796 = getelementptr i8, ptr %env, i64 32
  %v797 = load ptr, ptr %v796, align 8, !tbaa !3
  %v834 = call ptr @mlf_env_new(i64 1)
  %v835 = getelementptr i8, ptr %v834, i64 24
  store ptr %v797, ptr %v835, align 8, !tbaa !3
  %v836 = call ptr @mlf_thunk(ptr @mlf.code.798, ptr %v834)
  %v1251 = call ptr @mlf_env_new(i64 2)
  %v1252 = getelementptr i8, ptr %v1251, i64 24
  store ptr %v795, ptr %v1252, align 8, !tbaa !3
  %v1253 = getelementptr i8, ptr %v1251, i64 32
  store ptr %v797, ptr %v1253, align 8, !tbaa !3
  %v1254 = call ptr @mlf_closure(ptr @mlf.code.837, ptr %v1251)
  %v1255 = call ptr @mlf_prim2(i64 1, ptr %v836, ptr %v1254)
  ret ptr %v1255
}

define private ptr @mlf.code.749(ptr %env, ptr %arg) {
entry:
  %v750 = getelementptr i8, ptr %env, i64 24
  %v751 = load ptr, ptr %v750, align 8, !tbaa !3
  %v752 = getelementptr i8, ptr %env, i64 32
  %v753 = load ptr, ptr %v752, align 8, !tbaa !3
  %v790 = call ptr @mlf_env_new(i64 1)
  %v791 = getelementptr i8, ptr %v790, i64 24
  store ptr %v753, ptr %v791, align 8, !tbaa !3
  %v792 = call ptr @mlf_thunk(ptr @mlf.code.754, ptr %v790)
  %v1256 = call ptr @mlf_env_new(i64 2)
  %v1257 = getelementptr i8, ptr %v1256, i64 24
  store ptr %v751, ptr %v1257, align 8, !tbaa !3
  %v1258 = getelementptr i8, ptr %v1256, i64 32
  store ptr %v753, ptr %v1258, align 8, !tbaa !3
  %v1259 = call ptr @mlf_closure(ptr @mlf.code.793, ptr %v1256)
  %v1260 = call ptr @mlf_prim2(i64 1, ptr %v792, ptr %v1259)
  ret ptr %v1260
}

define private ptr @mlf.code.714(ptr %env, ptr %arg) {
entry:
  %v715 = getelementptr i8, ptr %env, i64 24
  %v716 = load ptr, ptr %v715, align 8, !tbaa !3
  %v717 = getelementptr i8, ptr %env, i64 32
  %v718 = load ptr, ptr %v717, align 8, !tbaa !3
  %v746 = call ptr @mlf_env_new(i64 1)
  %v747 = getelementptr i8, ptr %v746, i64 24
  store ptr %v718, ptr %v747, align 8, !tbaa !3
  %v748 = call ptr @mlf_thunk(ptr @mlf.code.719, ptr %v746)
  %v1261 = call ptr @mlf_env_new(i64 2)
  %v1262 = getelementptr i8, ptr %v1261, i64 24
  store ptr %v716, ptr %v1262, align 8, !tbaa !3
  %v1263 = getelementptr i8, ptr %v1261, i64 32
  store ptr %v718, ptr %v1263, align 8, !tbaa !3
  %v1264 = call ptr @mlf_closure(ptr @mlf.code.749, ptr %v1261)
  %v1265 = call ptr @mlf_prim2(i64 1, ptr %v748, ptr %v1264)
  ret ptr %v1265
}

define private ptr @mlf.code.679(ptr %env, ptr %arg) {
entry:
  %v680 = getelementptr i8, ptr %env, i64 24
  %v681 = load ptr, ptr %v680, align 8, !tbaa !3
  %v682 = getelementptr i8, ptr %env, i64 32
  %v683 = load ptr, ptr %v682, align 8, !tbaa !3
  %v711 = call ptr @mlf_env_new(i64 1)
  %v712 = getelementptr i8, ptr %v711, i64 24
  store ptr %v683, ptr %v712, align 8, !tbaa !3
  %v713 = call ptr @mlf_thunk(ptr @mlf.code.684, ptr %v711)
  %v1266 = call ptr @mlf_env_new(i64 2)
  %v1267 = getelementptr i8, ptr %v1266, i64 24
  store ptr %v681, ptr %v1267, align 8, !tbaa !3
  %v1268 = getelementptr i8, ptr %v1266, i64 32
  store ptr %v683, ptr %v1268, align 8, !tbaa !3
  %v1269 = call ptr @mlf_closure(ptr @mlf.code.714, ptr %v1266)
  %v1270 = call ptr @mlf_prim2(i64 1, ptr %v713, ptr %v1269)
  ret ptr %v1270
}

define private ptr @mlf.code.644(ptr %env, ptr %arg) {
entry:
  %v645 = getelementptr i8, ptr %env, i64 24
  %v646 = load ptr, ptr %v645, align 8, !tbaa !3
  %v647 = getelementptr i8, ptr %env, i64 32
  %v648 = load ptr, ptr %v647, align 8, !tbaa !3
  %v676 = call ptr @mlf_env_new(i64 1)
  %v677 = getelementptr i8, ptr %v676, i64 24
  store ptr %v648, ptr %v677, align 8, !tbaa !3
  %v678 = call ptr @mlf_thunk(ptr @mlf.code.649, ptr %v676)
  %v1271 = call ptr @mlf_env_new(i64 2)
  %v1272 = getelementptr i8, ptr %v1271, i64 24
  store ptr %v646, ptr %v1272, align 8, !tbaa !3
  %v1273 = getelementptr i8, ptr %v1271, i64 32
  store ptr %v648, ptr %v1273, align 8, !tbaa !3
  %v1274 = call ptr @mlf_closure(ptr @mlf.code.679, ptr %v1271)
  %v1275 = call ptr @mlf_prim2(i64 1, ptr %v678, ptr %v1274)
  ret ptr %v1275
}

define private ptr @mlf.code.593(ptr %env, ptr %arg) {
entry:
  %v594 = getelementptr i8, ptr %env, i64 24
  %v595 = load ptr, ptr %v594, align 8, !tbaa !3
  %v596 = getelementptr i8, ptr %env, i64 32
  %v597 = load ptr, ptr %v596, align 8, !tbaa !3
  %v640 = call ptr @mlf_env_new(i64 2)
  %v641 = getelementptr i8, ptr %v640, i64 24
  store ptr %v595, ptr %v641, align 8, !tbaa !3
  %v642 = getelementptr i8, ptr %v640, i64 32
  store ptr %v597, ptr %v642, align 8, !tbaa !3
  %v643 = call ptr @mlf_thunk(ptr @mlf.code.598, ptr %v640)
  %v1276 = call ptr @mlf_env_new(i64 2)
  %v1277 = getelementptr i8, ptr %v1276, i64 24
  store ptr %v595, ptr %v1277, align 8, !tbaa !3
  %v1278 = getelementptr i8, ptr %v1276, i64 32
  store ptr %v597, ptr %v1278, align 8, !tbaa !3
  %v1279 = call ptr @mlf_closure(ptr @mlf.code.644, ptr %v1276)
  %v1280 = call ptr @mlf_prim2(i64 1, ptr %v643, ptr %v1279)
  ret ptr %v1280
}

define private ptr @mlf.code.549(ptr %env, ptr %arg) {
entry:
  %v550 = getelementptr i8, ptr %env, i64 24
  %v551 = load ptr, ptr %v550, align 8, !tbaa !3
  %v552 = getelementptr i8, ptr %env, i64 32
  %v553 = load ptr, ptr %v552, align 8, !tbaa !3
  %v590 = call ptr @mlf_env_new(i64 1)
  %v591 = getelementptr i8, ptr %v590, i64 24
  store ptr %v553, ptr %v591, align 8, !tbaa !3
  %v592 = call ptr @mlf_thunk(ptr @mlf.code.554, ptr %v590)
  %v1281 = call ptr @mlf_env_new(i64 2)
  %v1282 = getelementptr i8, ptr %v1281, i64 24
  store ptr %v551, ptr %v1282, align 8, !tbaa !3
  %v1283 = getelementptr i8, ptr %v1281, i64 32
  store ptr %v553, ptr %v1283, align 8, !tbaa !3
  %v1284 = call ptr @mlf_closure(ptr @mlf.code.593, ptr %v1281)
  %v1285 = call ptr @mlf_prim2(i64 1, ptr %v592, ptr %v1284)
  ret ptr %v1285
}

define private ptr @mlf.code.505(ptr %env, ptr %arg) {
entry:
  %v506 = getelementptr i8, ptr %env, i64 24
  %v507 = load ptr, ptr %v506, align 8, !tbaa !3
  %v508 = getelementptr i8, ptr %env, i64 32
  %v509 = load ptr, ptr %v508, align 8, !tbaa !3
  %v546 = call ptr @mlf_env_new(i64 1)
  %v547 = getelementptr i8, ptr %v546, i64 24
  store ptr %v509, ptr %v547, align 8, !tbaa !3
  %v548 = call ptr @mlf_thunk(ptr @mlf.code.510, ptr %v546)
  %v1286 = call ptr @mlf_env_new(i64 2)
  %v1287 = getelementptr i8, ptr %v1286, i64 24
  store ptr %v507, ptr %v1287, align 8, !tbaa !3
  %v1288 = getelementptr i8, ptr %v1286, i64 32
  store ptr %v509, ptr %v1288, align 8, !tbaa !3
  %v1289 = call ptr @mlf_closure(ptr @mlf.code.549, ptr %v1286)
  %v1290 = call ptr @mlf_prim2(i64 1, ptr %v548, ptr %v1289)
  ret ptr %v1290
}

define private ptr @mlf.code.461(ptr %env, ptr %arg) {
entry:
  %v462 = getelementptr i8, ptr %env, i64 24
  %v463 = load ptr, ptr %v462, align 8, !tbaa !3
  %v464 = getelementptr i8, ptr %env, i64 32
  %v465 = load ptr, ptr %v464, align 8, !tbaa !3
  %v502 = call ptr @mlf_env_new(i64 1)
  %v503 = getelementptr i8, ptr %v502, i64 24
  store ptr %v465, ptr %v503, align 8, !tbaa !3
  %v504 = call ptr @mlf_thunk(ptr @mlf.code.466, ptr %v502)
  %v1291 = call ptr @mlf_env_new(i64 2)
  %v1292 = getelementptr i8, ptr %v1291, i64 24
  store ptr %v463, ptr %v1292, align 8, !tbaa !3
  %v1293 = getelementptr i8, ptr %v1291, i64 32
  store ptr %v465, ptr %v1293, align 8, !tbaa !3
  %v1294 = call ptr @mlf_closure(ptr @mlf.code.505, ptr %v1291)
  %v1295 = call ptr @mlf_prim2(i64 1, ptr %v504, ptr %v1294)
  ret ptr %v1295
}

define private ptr @mlf.code.426(ptr %env, ptr %arg) {
entry:
  %v427 = getelementptr i8, ptr %env, i64 24
  %v428 = load ptr, ptr %v427, align 8, !tbaa !3
  %v429 = getelementptr i8, ptr %env, i64 32
  %v430 = load ptr, ptr %v429, align 8, !tbaa !3
  %v458 = call ptr @mlf_env_new(i64 1)
  %v459 = getelementptr i8, ptr %v458, i64 24
  store ptr %v430, ptr %v459, align 8, !tbaa !3
  %v460 = call ptr @mlf_thunk(ptr @mlf.code.431, ptr %v458)
  %v1296 = call ptr @mlf_env_new(i64 2)
  %v1297 = getelementptr i8, ptr %v1296, i64 24
  store ptr %v428, ptr %v1297, align 8, !tbaa !3
  %v1298 = getelementptr i8, ptr %v1296, i64 32
  store ptr %v430, ptr %v1298, align 8, !tbaa !3
  %v1299 = call ptr @mlf_closure(ptr @mlf.code.461, ptr %v1296)
  %v1300 = call ptr @mlf_prim2(i64 1, ptr %v460, ptr %v1299)
  ret ptr %v1300
}

define private ptr @mlf.code.391(ptr %env, ptr %arg) {
entry:
  %v392 = getelementptr i8, ptr %env, i64 24
  %v393 = load ptr, ptr %v392, align 8, !tbaa !3
  %v394 = getelementptr i8, ptr %env, i64 32
  %v395 = load ptr, ptr %v394, align 8, !tbaa !3
  %v423 = call ptr @mlf_env_new(i64 1)
  %v424 = getelementptr i8, ptr %v423, i64 24
  store ptr %v395, ptr %v424, align 8, !tbaa !3
  %v425 = call ptr @mlf_thunk(ptr @mlf.code.396, ptr %v423)
  %v1301 = call ptr @mlf_env_new(i64 2)
  %v1302 = getelementptr i8, ptr %v1301, i64 24
  store ptr %v393, ptr %v1302, align 8, !tbaa !3
  %v1303 = getelementptr i8, ptr %v1301, i64 32
  store ptr %v395, ptr %v1303, align 8, !tbaa !3
  %v1304 = call ptr @mlf_closure(ptr @mlf.code.426, ptr %v1301)
  %v1305 = call ptr @mlf_prim2(i64 1, ptr %v425, ptr %v1304)
  ret ptr %v1305
}

define private ptr @mlf.code.356(ptr %env, ptr %arg) {
entry:
  %v357 = getelementptr i8, ptr %env, i64 24
  %v358 = load ptr, ptr %v357, align 8, !tbaa !3
  %v359 = getelementptr i8, ptr %env, i64 32
  %v360 = load ptr, ptr %v359, align 8, !tbaa !3
  %v388 = call ptr @mlf_env_new(i64 1)
  %v389 = getelementptr i8, ptr %v388, i64 24
  store ptr %v360, ptr %v389, align 8, !tbaa !3
  %v390 = call ptr @mlf_thunk(ptr @mlf.code.361, ptr %v388)
  %v1306 = call ptr @mlf_env_new(i64 2)
  %v1307 = getelementptr i8, ptr %v1306, i64 24
  store ptr %v358, ptr %v1307, align 8, !tbaa !3
  %v1308 = getelementptr i8, ptr %v1306, i64 32
  store ptr %v360, ptr %v1308, align 8, !tbaa !3
  %v1309 = call ptr @mlf_closure(ptr @mlf.code.391, ptr %v1306)
  %v1310 = call ptr @mlf_prim2(i64 1, ptr %v390, ptr %v1309)
  ret ptr %v1310
}

define private ptr @mlf.code.305(ptr %env, ptr %arg) {
entry:
  %v306 = getelementptr i8, ptr %env, i64 24
  %v307 = load ptr, ptr %v306, align 8, !tbaa !3
  %v308 = getelementptr i8, ptr %env, i64 32
  %v309 = load ptr, ptr %v308, align 8, !tbaa !3
  %v352 = call ptr @mlf_env_new(i64 2)
  %v353 = getelementptr i8, ptr %v352, i64 24
  store ptr %v307, ptr %v353, align 8, !tbaa !3
  %v354 = getelementptr i8, ptr %v352, i64 32
  store ptr %v309, ptr %v354, align 8, !tbaa !3
  %v355 = call ptr @mlf_thunk(ptr @mlf.code.310, ptr %v352)
  %v1311 = call ptr @mlf_env_new(i64 2)
  %v1312 = getelementptr i8, ptr %v1311, i64 24
  store ptr %v307, ptr %v1312, align 8, !tbaa !3
  %v1313 = getelementptr i8, ptr %v1311, i64 32
  store ptr %v309, ptr %v1313, align 8, !tbaa !3
  %v1314 = call ptr @mlf_closure(ptr @mlf.code.356, ptr %v1311)
  %v1315 = call ptr @mlf_prim2(i64 1, ptr %v355, ptr %v1314)
  ret ptr %v1315
}

define private ptr @mlf.code.261(ptr %env, ptr %arg) {
entry:
  %v262 = getelementptr i8, ptr %env, i64 24
  %v263 = load ptr, ptr %v262, align 8, !tbaa !3
  %v264 = getelementptr i8, ptr %env, i64 32
  %v265 = load ptr, ptr %v264, align 8, !tbaa !3
  %v302 = call ptr @mlf_env_new(i64 1)
  %v303 = getelementptr i8, ptr %v302, i64 24
  store ptr %v265, ptr %v303, align 8, !tbaa !3
  %v304 = call ptr @mlf_thunk(ptr @mlf.code.266, ptr %v302)
  %v1316 = call ptr @mlf_env_new(i64 2)
  %v1317 = getelementptr i8, ptr %v1316, i64 24
  store ptr %v263, ptr %v1317, align 8, !tbaa !3
  %v1318 = getelementptr i8, ptr %v1316, i64 32
  store ptr %v265, ptr %v1318, align 8, !tbaa !3
  %v1319 = call ptr @mlf_closure(ptr @mlf.code.305, ptr %v1316)
  %v1320 = call ptr @mlf_prim2(i64 1, ptr %v304, ptr %v1319)
  ret ptr %v1320
}

define private ptr @mlf.code.217(ptr %env, ptr %arg) {
entry:
  %v218 = getelementptr i8, ptr %env, i64 24
  %v219 = load ptr, ptr %v218, align 8, !tbaa !3
  %v220 = getelementptr i8, ptr %env, i64 32
  %v221 = load ptr, ptr %v220, align 8, !tbaa !3
  %v258 = call ptr @mlf_env_new(i64 1)
  %v259 = getelementptr i8, ptr %v258, i64 24
  store ptr %v221, ptr %v259, align 8, !tbaa !3
  %v260 = call ptr @mlf_thunk(ptr @mlf.code.222, ptr %v258)
  %v1321 = call ptr @mlf_env_new(i64 2)
  %v1322 = getelementptr i8, ptr %v1321, i64 24
  store ptr %v219, ptr %v1322, align 8, !tbaa !3
  %v1323 = getelementptr i8, ptr %v1321, i64 32
  store ptr %v221, ptr %v1323, align 8, !tbaa !3
  %v1324 = call ptr @mlf_closure(ptr @mlf.code.261, ptr %v1321)
  %v1325 = call ptr @mlf_prim2(i64 1, ptr %v260, ptr %v1324)
  ret ptr %v1325
}

define private ptr @mlf.code.173(ptr %env, ptr %arg) {
entry:
  %v174 = getelementptr i8, ptr %env, i64 24
  %v175 = load ptr, ptr %v174, align 8, !tbaa !3
  %v176 = getelementptr i8, ptr %env, i64 32
  %v177 = load ptr, ptr %v176, align 8, !tbaa !3
  %v214 = call ptr @mlf_env_new(i64 1)
  %v215 = getelementptr i8, ptr %v214, i64 24
  store ptr %v177, ptr %v215, align 8, !tbaa !3
  %v216 = call ptr @mlf_thunk(ptr @mlf.code.178, ptr %v214)
  %v1326 = call ptr @mlf_env_new(i64 2)
  %v1327 = getelementptr i8, ptr %v1326, i64 24
  store ptr %v175, ptr %v1327, align 8, !tbaa !3
  %v1328 = getelementptr i8, ptr %v1326, i64 32
  store ptr %v177, ptr %v1328, align 8, !tbaa !3
  %v1329 = call ptr @mlf_closure(ptr @mlf.code.217, ptr %v1326)
  %v1330 = call ptr @mlf_prim2(i64 1, ptr %v216, ptr %v1329)
  ret ptr %v1330
}

define private ptr @mlf.code.138(ptr %env, ptr %arg) {
entry:
  %v139 = getelementptr i8, ptr %env, i64 24
  %v140 = load ptr, ptr %v139, align 8, !tbaa !3
  %v141 = getelementptr i8, ptr %env, i64 32
  %v142 = load ptr, ptr %v141, align 8, !tbaa !3
  %v170 = call ptr @mlf_env_new(i64 1)
  %v171 = getelementptr i8, ptr %v170, i64 24
  store ptr %v142, ptr %v171, align 8, !tbaa !3
  %v172 = call ptr @mlf_thunk(ptr @mlf.code.143, ptr %v170)
  %v1331 = call ptr @mlf_env_new(i64 2)
  %v1332 = getelementptr i8, ptr %v1331, i64 24
  store ptr %v140, ptr %v1332, align 8, !tbaa !3
  %v1333 = getelementptr i8, ptr %v1331, i64 32
  store ptr %v142, ptr %v1333, align 8, !tbaa !3
  %v1334 = call ptr @mlf_closure(ptr @mlf.code.173, ptr %v1331)
  %v1335 = call ptr @mlf_prim2(i64 1, ptr %v172, ptr %v1334)
  ret ptr %v1335
}

define private ptr @mlf.code.103(ptr %env, ptr %arg) {
entry:
  %v104 = getelementptr i8, ptr %env, i64 24
  %v105 = load ptr, ptr %v104, align 8, !tbaa !3
  %v106 = getelementptr i8, ptr %env, i64 32
  %v107 = load ptr, ptr %v106, align 8, !tbaa !3
  %v135 = call ptr @mlf_env_new(i64 1)
  %v136 = getelementptr i8, ptr %v135, i64 24
  store ptr %v107, ptr %v136, align 8, !tbaa !3
  %v137 = call ptr @mlf_thunk(ptr @mlf.code.108, ptr %v135)
  %v1336 = call ptr @mlf_env_new(i64 2)
  %v1337 = getelementptr i8, ptr %v1336, i64 24
  store ptr %v105, ptr %v1337, align 8, !tbaa !3
  %v1338 = getelementptr i8, ptr %v1336, i64 32
  store ptr %v107, ptr %v1338, align 8, !tbaa !3
  %v1339 = call ptr @mlf_closure(ptr @mlf.code.138, ptr %v1336)
  %v1340 = call ptr @mlf_prim2(i64 1, ptr %v137, ptr %v1339)
  ret ptr %v1340
}

define private ptr @mlf.code.68(ptr %env, ptr %arg) {
entry:
  %v69 = getelementptr i8, ptr %env, i64 24
  %v70 = load ptr, ptr %v69, align 8, !tbaa !3
  %v71 = getelementptr i8, ptr %env, i64 32
  %v72 = load ptr, ptr %v71, align 8, !tbaa !3
  %v100 = call ptr @mlf_env_new(i64 1)
  %v101 = getelementptr i8, ptr %v100, i64 24
  store ptr %v72, ptr %v101, align 8, !tbaa !3
  %v102 = call ptr @mlf_thunk(ptr @mlf.code.73, ptr %v100)
  %v1341 = call ptr @mlf_env_new(i64 2)
  %v1342 = getelementptr i8, ptr %v1341, i64 24
  store ptr %v70, ptr %v1342, align 8, !tbaa !3
  %v1343 = getelementptr i8, ptr %v1341, i64 32
  store ptr %v72, ptr %v1343, align 8, !tbaa !3
  %v1344 = call ptr @mlf_closure(ptr @mlf.code.103, ptr %v1341)
  %v1345 = call ptr @mlf_prim2(i64 1, ptr %v102, ptr %v1344)
  ret ptr %v1345
}

define private ptr @mlf.code.31(ptr %env, ptr %arg) {
entry:
  %v32 = getelementptr i8, ptr %env, i64 24
  %v33 = load ptr, ptr %v32, align 8, !tbaa !3
  %v34 = getelementptr i8, ptr %env, i64 32
  %v35 = load ptr, ptr %v34, align 8, !tbaa !3
  %v64 = call ptr @mlf_env_new(i64 2)
  %v65 = getelementptr i8, ptr %v64, i64 24
  store ptr %v33, ptr %v65, align 8, !tbaa !3
  %v66 = getelementptr i8, ptr %v64, i64 32
  store ptr %v35, ptr %v66, align 8, !tbaa !3
  %v67 = call ptr @mlf_thunk(ptr @mlf.code.36, ptr %v64)
  %v1346 = call ptr @mlf_env_new(i64 2)
  %v1347 = getelementptr i8, ptr %v1346, i64 24
  store ptr %v33, ptr %v1347, align 8, !tbaa !3
  %v1348 = getelementptr i8, ptr %v1346, i64 32
  store ptr %v35, ptr %v1348, align 8, !tbaa !3
  %v1349 = call ptr @mlf_closure(ptr @mlf.code.68, ptr %v1346)
  %v1350 = call ptr @mlf_prim2(i64 1, ptr %v67, ptr %v1349)
  ret ptr %v1350
}

define private ptr @mlf.numeric.1.pppddd(ptr %a0, ptr %a1, ptr %a2, double %a3, double %a4, double %a5) alwaysinline {
entry:
  %v1617 = ptrtoint ptr %a2 to i64
  %v1618 = ptrtoint ptr inttoptr (i64 71 to ptr) to i64
  %v1619 = and i64 %v1617, %v1618
  %v1620 = and i64 %v1619, 1
  %v1621 = icmp ne i64 %v1620, 0
  br i1 %v1621, label %yes.1622, label %no.1623
yes.1622:
  %v1625 = icmp eq i64 %v1617, %v1618
  %v1626 = select i1 %v1625, ptr inttoptr (i64 6 to ptr), ptr inttoptr (i64 2 to ptr)
  br label %join.1624
no.1623:
  %v1627 = call ptr @mlf_eq_int(ptr %a2, ptr inttoptr (i64 71 to ptr))
  br label %join.1624
join.1624:
  %v1628 = phi ptr [ %v1626, %yes.1622 ], [ %v1627, %no.1623 ]
  %v1629 = icmp eq ptr %v1628, inttoptr (i64 6 to ptr)
  br i1 %v1629, label %tail.yes.1630, label %tail.no.1631
tail.yes.1630:
  %v1632 = fsub double 0x0000000000000000, %a3
  %v1633 = getelementptr i8, ptr %a0, i64 24
  %v1634 = load double, ptr %v1633, align 8, !tbaa !3
  %v1635 = fdiv double %v1632, %v1634
  %v1636 = getelementptr i8, ptr %a1, i64 24
  %v1637 = load i64, ptr %v1636, align 8, !tbaa !3
  %v1638 = getelementptr i8, ptr %a1, i64 32
  %v1639 = load ptr, ptr %v1638, align 8, !tbaa !3
  %v1640 = ptrtoint ptr inttoptr (i64 7 to ptr) to i64
  %v1641 = ashr i64 %v1640, 1
  %v1642 = and i64 %v1640, 1
  %v1643 = icmp ne i64 %v1642, 0
  %v1644 = icmp ult i64 %v1641, %v1637
  %v1645 = and i1 %v1643, %v1644
  br i1 %v1645, label %array.valid.1646, label %array.invalid.1647
array.invalid.1647:
  call void @mlf_bounds_failure()
  unreachable
array.valid.1646:
  %v1648 = getelementptr i64, ptr %v1639, i64 %v1641
  store double %v1635, ptr %v1648, align 8, !tbaa !4
  %v1649 = fsub double 0x0000000000000000, %a4
  %v1650 = fdiv double %v1649, %v1634
  %v1651 = ptrtoint ptr inttoptr (i64 9 to ptr) to i64
  %v1652 = ashr i64 %v1651, 1
  %v1653 = and i64 %v1651, 1
  %v1654 = icmp ne i64 %v1653, 0
  %v1655 = icmp ult i64 %v1652, %v1637
  %v1656 = and i1 %v1654, %v1655
  br i1 %v1656, label %array.valid.1657, label %array.invalid.1658
array.invalid.1658:
  call void @mlf_bounds_failure()
  unreachable
array.valid.1657:
  %v1659 = getelementptr i64, ptr %v1639, i64 %v1652
  store double %v1650, ptr %v1659, align 8, !tbaa !4
  %v1660 = fsub double 0x0000000000000000, %a5
  %v1661 = fdiv double %v1660, %v1634
  %v1662 = ptrtoint ptr inttoptr (i64 11 to ptr) to i64
  %v1663 = ashr i64 %v1662, 1
  %v1664 = and i64 %v1662, 1
  %v1665 = icmp ne i64 %v1664, 0
  %v1666 = icmp ult i64 %v1663, %v1637
  %v1667 = and i1 %v1665, %v1666
  br i1 %v1667, label %array.valid.1668, label %array.invalid.1669
array.invalid.1669:
  call void @mlf_bounds_failure()
  unreachable
array.valid.1668:
  %v1670 = getelementptr i64, ptr %v1639, i64 %v1663
  store double %v1661, ptr %v1670, align 8, !tbaa !4
  ret ptr inttoptr (i64 4 to ptr)
tail.no.1631:
  %v1671 = ptrtoint ptr %a2 to i64
  %v1672 = ptrtoint ptr inttoptr (i64 7 to ptr) to i64
  %v1673 = and i64 %v1671, %v1672
  %v1674 = and i64 %v1673, 1
  %v1675 = icmp ne i64 %v1674, 0
  br i1 %v1675, label %yes.1676, label %no.1677
yes.1676:
  %v1679 = sub i64 %v1672, 1
  %v1680 = call { i64, i1 } @llvm.sadd.with.overflow.i64(i64 %v1671, i64 %v1679)
  %v1681 = extractvalue { i64, i1 } %v1680, 0
  %v1682 = extractvalue { i64, i1 } %v1680, 1
  br i1 %v1682, label %yes.1683, label %no.1684
yes.1683:
  %v1686 = call ptr @mlf_add_int(ptr %a2, ptr inttoptr (i64 7 to ptr))
  br label %join.1685
no.1684:
  %v1687 = inttoptr i64 %v1681 to ptr
  br label %join.1685
join.1685:
  %v1688 = phi ptr [ %v1686, %yes.1683 ], [ %v1687, %no.1684 ]
  br label %join.1678
no.1677:
  %v1689 = call ptr @mlf_add_int(ptr %a2, ptr inttoptr (i64 7 to ptr))
  br label %join.1678
join.1678:
  %v1690 = phi ptr [ %v1688, %join.1685 ], [ %v1689, %no.1677 ]
  %v1691 = getelementptr i8, ptr %a1, i64 24
  %v1692 = load i64, ptr %v1691, align 8, !tbaa !3
  %v1693 = getelementptr i8, ptr %a1, i64 32
  %v1694 = load ptr, ptr %v1693, align 8, !tbaa !3
  %v1695 = ptrtoint ptr %v1690 to i64
  %v1696 = ashr i64 %v1695, 1
  %v1697 = and i64 %v1695, 1
  %v1698 = icmp ne i64 %v1697, 0
  %v1699 = icmp ult i64 %v1696, %v1692
  %v1700 = and i1 %v1698, %v1699
  br i1 %v1700, label %array.valid.1701, label %array.invalid.1702
array.invalid.1702:
  call void @mlf_bounds_failure()
  unreachable
array.valid.1701:
  %v1703 = getelementptr i64, ptr %v1694, i64 %v1696
  %v1704 = load double, ptr %v1703, align 8, !tbaa !4
  %v1705 = ptrtoint ptr %a2 to i64
  %v1706 = ptrtoint ptr inttoptr (i64 9 to ptr) to i64
  %v1707 = and i64 %v1705, %v1706
  %v1708 = and i64 %v1707, 1
  %v1709 = icmp ne i64 %v1708, 0
  br i1 %v1709, label %yes.1710, label %no.1711
yes.1710:
  %v1713 = sub i64 %v1706, 1
  %v1714 = call { i64, i1 } @llvm.sadd.with.overflow.i64(i64 %v1705, i64 %v1713)
  %v1715 = extractvalue { i64, i1 } %v1714, 0
  %v1716 = extractvalue { i64, i1 } %v1714, 1
  br i1 %v1716, label %yes.1717, label %no.1718
yes.1717:
  %v1720 = call ptr @mlf_add_int(ptr %a2, ptr inttoptr (i64 9 to ptr))
  br label %join.1719
no.1718:
  %v1721 = inttoptr i64 %v1715 to ptr
  br label %join.1719
join.1719:
  %v1722 = phi ptr [ %v1720, %yes.1717 ], [ %v1721, %no.1718 ]
  br label %join.1712
no.1711:
  %v1723 = call ptr @mlf_add_int(ptr %a2, ptr inttoptr (i64 9 to ptr))
  br label %join.1712
join.1712:
  %v1724 = phi ptr [ %v1722, %join.1719 ], [ %v1723, %no.1711 ]
  %v1725 = ptrtoint ptr %v1724 to i64
  %v1726 = ashr i64 %v1725, 1
  %v1727 = and i64 %v1725, 1
  %v1728 = icmp ne i64 %v1727, 0
  %v1729 = icmp ult i64 %v1726, %v1692
  %v1730 = and i1 %v1728, %v1729
  br i1 %v1730, label %array.valid.1731, label %array.invalid.1732
array.invalid.1732:
  call void @mlf_bounds_failure()
  unreachable
array.valid.1731:
  %v1733 = getelementptr i64, ptr %v1694, i64 %v1726
  %v1734 = load double, ptr %v1733, align 8, !tbaa !4
  %v1735 = ptrtoint ptr %a2 to i64
  %v1736 = ptrtoint ptr inttoptr (i64 11 to ptr) to i64
  %v1737 = and i64 %v1735, %v1736
  %v1738 = and i64 %v1737, 1
  %v1739 = icmp ne i64 %v1738, 0
  br i1 %v1739, label %yes.1740, label %no.1741
yes.1740:
  %v1743 = sub i64 %v1736, 1
  %v1744 = call { i64, i1 } @llvm.sadd.with.overflow.i64(i64 %v1735, i64 %v1743)
  %v1745 = extractvalue { i64, i1 } %v1744, 0
  %v1746 = extractvalue { i64, i1 } %v1744, 1
  br i1 %v1746, label %yes.1747, label %no.1748
yes.1747:
  %v1750 = call ptr @mlf_add_int(ptr %a2, ptr inttoptr (i64 11 to ptr))
  br label %join.1749
no.1748:
  %v1751 = inttoptr i64 %v1745 to ptr
  br label %join.1749
join.1749:
  %v1752 = phi ptr [ %v1750, %yes.1747 ], [ %v1751, %no.1748 ]
  br label %join.1742
no.1741:
  %v1753 = call ptr @mlf_add_int(ptr %a2, ptr inttoptr (i64 11 to ptr))
  br label %join.1742
join.1742:
  %v1754 = phi ptr [ %v1752, %join.1749 ], [ %v1753, %no.1741 ]
  %v1755 = ptrtoint ptr %v1754 to i64
  %v1756 = ashr i64 %v1755, 1
  %v1757 = and i64 %v1755, 1
  %v1758 = icmp ne i64 %v1757, 0
  %v1759 = icmp ult i64 %v1756, %v1692
  %v1760 = and i1 %v1758, %v1759
  br i1 %v1760, label %array.valid.1761, label %array.invalid.1762
array.invalid.1762:
  call void @mlf_bounds_failure()
  unreachable
array.valid.1761:
  %v1763 = getelementptr i64, ptr %v1694, i64 %v1756
  %v1764 = load double, ptr %v1763, align 8, !tbaa !4
  %v1765 = ptrtoint ptr %a2 to i64
  %v1766 = ptrtoint ptr inttoptr (i64 13 to ptr) to i64
  %v1767 = and i64 %v1765, %v1766
  %v1768 = and i64 %v1767, 1
  %v1769 = icmp ne i64 %v1768, 0
  br i1 %v1769, label %yes.1770, label %no.1771
yes.1770:
  %v1773 = sub i64 %v1766, 1
  %v1774 = call { i64, i1 } @llvm.sadd.with.overflow.i64(i64 %v1765, i64 %v1773)
  %v1775 = extractvalue { i64, i1 } %v1774, 0
  %v1776 = extractvalue { i64, i1 } %v1774, 1
  br i1 %v1776, label %yes.1777, label %no.1778
yes.1777:
  %v1780 = call ptr @mlf_add_int(ptr %a2, ptr inttoptr (i64 13 to ptr))
  br label %join.1779
no.1778:
  %v1781 = inttoptr i64 %v1775 to ptr
  br label %join.1779
join.1779:
  %v1782 = phi ptr [ %v1780, %yes.1777 ], [ %v1781, %no.1778 ]
  br label %join.1772
no.1771:
  %v1783 = call ptr @mlf_add_int(ptr %a2, ptr inttoptr (i64 13 to ptr))
  br label %join.1772
join.1772:
  %v1784 = phi ptr [ %v1782, %join.1779 ], [ %v1783, %no.1771 ]
  %v1785 = ptrtoint ptr %v1784 to i64
  %v1786 = ashr i64 %v1785, 1
  %v1787 = and i64 %v1785, 1
  %v1788 = icmp ne i64 %v1787, 0
  %v1789 = icmp ult i64 %v1786, %v1692
  %v1790 = and i1 %v1788, %v1789
  br i1 %v1790, label %array.valid.1791, label %array.invalid.1792
array.invalid.1792:
  call void @mlf_bounds_failure()
  unreachable
array.valid.1791:
  %v1793 = getelementptr i64, ptr %v1694, i64 %v1786
  %v1794 = load double, ptr %v1793, align 8, !tbaa !4
  %v1795 = ptrtoint ptr %a2 to i64
  %v1796 = ptrtoint ptr inttoptr (i64 15 to ptr) to i64
  %v1797 = and i64 %v1795, %v1796
  %v1798 = and i64 %v1797, 1
  %v1799 = icmp ne i64 %v1798, 0
  br i1 %v1799, label %yes.1800, label %no.1801
yes.1800:
  %v1803 = sub i64 %v1796, 1
  %v1804 = call { i64, i1 } @llvm.sadd.with.overflow.i64(i64 %v1795, i64 %v1803)
  %v1805 = extractvalue { i64, i1 } %v1804, 0
  %v1806 = extractvalue { i64, i1 } %v1804, 1
  br i1 %v1806, label %yes.1807, label %no.1808
yes.1807:
  %v1810 = call ptr @mlf_add_int(ptr %a2, ptr inttoptr (i64 15 to ptr))
  br label %join.1809
no.1808:
  %v1811 = inttoptr i64 %v1805 to ptr
  br label %join.1809
join.1809:
  %v1812 = phi ptr [ %v1810, %yes.1807 ], [ %v1811, %no.1808 ]
  br label %join.1802
no.1801:
  %v1813 = call ptr @mlf_add_int(ptr %a2, ptr inttoptr (i64 15 to ptr))
  br label %join.1802
join.1802:
  %v1814 = phi ptr [ %v1812, %join.1809 ], [ %v1813, %no.1801 ]
  %v1815 = fmul double %v1704, %v1794
  %v1816 = fadd double %a3, %v1815
  %v1817 = fmul double %v1734, %v1794
  %v1818 = fadd double %a4, %v1817
  %v1819 = fmul double %v1764, %v1794
  %v1820 = fadd double %a5, %v1819
  %v1821 = musttail call ptr @mlf.numeric.1.pppddd(ptr %a0, ptr %a1, ptr %v1814, double %v1816, double %v1818, double %v1820)
  ret ptr %v1821
}

define private ptr @mlf.numeric.1(ptr %a0, ptr %a1, ptr %a2, ptr %a3, ptr %a4, ptr %a5) alwaysinline {
entry:
  %v1401 = ptrtoint ptr %a2 to i64
  %v1402 = ptrtoint ptr inttoptr (i64 71 to ptr) to i64
  %v1403 = and i64 %v1401, %v1402
  %v1404 = and i64 %v1403, 1
  %v1405 = icmp ne i64 %v1404, 0
  br i1 %v1405, label %yes.1406, label %no.1407
yes.1406:
  %v1409 = icmp eq i64 %v1401, %v1402
  %v1410 = select i1 %v1409, ptr inttoptr (i64 6 to ptr), ptr inttoptr (i64 2 to ptr)
  br label %join.1408
no.1407:
  %v1411 = call ptr @mlf_eq_int(ptr %a2, ptr inttoptr (i64 71 to ptr))
  br label %join.1408
join.1408:
  %v1412 = phi ptr [ %v1410, %yes.1406 ], [ %v1411, %no.1407 ]
  %v1413 = icmp eq ptr %v1412, inttoptr (i64 6 to ptr)
  br i1 %v1413, label %tail.yes.1414, label %tail.no.1415
tail.yes.1414:
  %v1416 = getelementptr i8, ptr %a3, i64 24
  %v1417 = load double, ptr %v1416, align 8, !tbaa !3
  %v1418 = fsub double 0x0000000000000000, %v1417
  %v1419 = getelementptr i8, ptr %a0, i64 24
  %v1420 = load double, ptr %v1419, align 8, !tbaa !3
  %v1421 = fdiv double %v1418, %v1420
  %v1422 = getelementptr i8, ptr %a1, i64 24
  %v1423 = load i64, ptr %v1422, align 8, !tbaa !3
  %v1424 = getelementptr i8, ptr %a1, i64 32
  %v1425 = load ptr, ptr %v1424, align 8, !tbaa !3
  %v1426 = ptrtoint ptr inttoptr (i64 7 to ptr) to i64
  %v1427 = ashr i64 %v1426, 1
  %v1428 = and i64 %v1426, 1
  %v1429 = icmp ne i64 %v1428, 0
  %v1430 = icmp ult i64 %v1427, %v1423
  %v1431 = and i1 %v1429, %v1430
  br i1 %v1431, label %array.valid.1432, label %array.invalid.1433
array.invalid.1433:
  call void @mlf_bounds_failure()
  unreachable
array.valid.1432:
  %v1434 = getelementptr i64, ptr %v1425, i64 %v1427
  store double %v1421, ptr %v1434, align 8, !tbaa !4
  %v1435 = getelementptr i8, ptr %a4, i64 24
  %v1436 = load double, ptr %v1435, align 8, !tbaa !3
  %v1437 = fsub double 0x0000000000000000, %v1436
  %v1438 = fdiv double %v1437, %v1420
  %v1439 = ptrtoint ptr inttoptr (i64 9 to ptr) to i64
  %v1440 = ashr i64 %v1439, 1
  %v1441 = and i64 %v1439, 1
  %v1442 = icmp ne i64 %v1441, 0
  %v1443 = icmp ult i64 %v1440, %v1423
  %v1444 = and i1 %v1442, %v1443
  br i1 %v1444, label %array.valid.1445, label %array.invalid.1446
array.invalid.1446:
  call void @mlf_bounds_failure()
  unreachable
array.valid.1445:
  %v1447 = getelementptr i64, ptr %v1425, i64 %v1440
  store double %v1438, ptr %v1447, align 8, !tbaa !4
  %v1448 = getelementptr i8, ptr %a5, i64 24
  %v1449 = load double, ptr %v1448, align 8, !tbaa !3
  %v1450 = fsub double 0x0000000000000000, %v1449
  %v1451 = fdiv double %v1450, %v1420
  %v1452 = ptrtoint ptr inttoptr (i64 11 to ptr) to i64
  %v1453 = ashr i64 %v1452, 1
  %v1454 = and i64 %v1452, 1
  %v1455 = icmp ne i64 %v1454, 0
  %v1456 = icmp ult i64 %v1453, %v1423
  %v1457 = and i1 %v1455, %v1456
  br i1 %v1457, label %array.valid.1458, label %array.invalid.1459
array.invalid.1459:
  call void @mlf_bounds_failure()
  unreachable
array.valid.1458:
  %v1460 = getelementptr i64, ptr %v1425, i64 %v1453
  store double %v1451, ptr %v1460, align 8, !tbaa !4
  ret ptr inttoptr (i64 4 to ptr)
tail.no.1415:
  %v1461 = ptrtoint ptr %a2 to i64
  %v1462 = ptrtoint ptr inttoptr (i64 7 to ptr) to i64
  %v1463 = and i64 %v1461, %v1462
  %v1464 = and i64 %v1463, 1
  %v1465 = icmp ne i64 %v1464, 0
  br i1 %v1465, label %yes.1466, label %no.1467
yes.1466:
  %v1469 = sub i64 %v1462, 1
  %v1470 = call { i64, i1 } @llvm.sadd.with.overflow.i64(i64 %v1461, i64 %v1469)
  %v1471 = extractvalue { i64, i1 } %v1470, 0
  %v1472 = extractvalue { i64, i1 } %v1470, 1
  br i1 %v1472, label %yes.1473, label %no.1474
yes.1473:
  %v1476 = call ptr @mlf_add_int(ptr %a2, ptr inttoptr (i64 7 to ptr))
  br label %join.1475
no.1474:
  %v1477 = inttoptr i64 %v1471 to ptr
  br label %join.1475
join.1475:
  %v1478 = phi ptr [ %v1476, %yes.1473 ], [ %v1477, %no.1474 ]
  br label %join.1468
no.1467:
  %v1479 = call ptr @mlf_add_int(ptr %a2, ptr inttoptr (i64 7 to ptr))
  br label %join.1468
join.1468:
  %v1480 = phi ptr [ %v1478, %join.1475 ], [ %v1479, %no.1467 ]
  %v1481 = getelementptr i8, ptr %a1, i64 24
  %v1482 = load i64, ptr %v1481, align 8, !tbaa !3
  %v1483 = getelementptr i8, ptr %a1, i64 32
  %v1484 = load ptr, ptr %v1483, align 8, !tbaa !3
  %v1485 = ptrtoint ptr %v1480 to i64
  %v1486 = ashr i64 %v1485, 1
  %v1487 = and i64 %v1485, 1
  %v1488 = icmp ne i64 %v1487, 0
  %v1489 = icmp ult i64 %v1486, %v1482
  %v1490 = and i1 %v1488, %v1489
  br i1 %v1490, label %array.valid.1491, label %array.invalid.1492
array.invalid.1492:
  call void @mlf_bounds_failure()
  unreachable
array.valid.1491:
  %v1493 = getelementptr i64, ptr %v1484, i64 %v1486
  %v1494 = load double, ptr %v1493, align 8, !tbaa !4
  %v1495 = ptrtoint ptr %a2 to i64
  %v1496 = ptrtoint ptr inttoptr (i64 9 to ptr) to i64
  %v1497 = and i64 %v1495, %v1496
  %v1498 = and i64 %v1497, 1
  %v1499 = icmp ne i64 %v1498, 0
  br i1 %v1499, label %yes.1500, label %no.1501
yes.1500:
  %v1503 = sub i64 %v1496, 1
  %v1504 = call { i64, i1 } @llvm.sadd.with.overflow.i64(i64 %v1495, i64 %v1503)
  %v1505 = extractvalue { i64, i1 } %v1504, 0
  %v1506 = extractvalue { i64, i1 } %v1504, 1
  br i1 %v1506, label %yes.1507, label %no.1508
yes.1507:
  %v1510 = call ptr @mlf_add_int(ptr %a2, ptr inttoptr (i64 9 to ptr))
  br label %join.1509
no.1508:
  %v1511 = inttoptr i64 %v1505 to ptr
  br label %join.1509
join.1509:
  %v1512 = phi ptr [ %v1510, %yes.1507 ], [ %v1511, %no.1508 ]
  br label %join.1502
no.1501:
  %v1513 = call ptr @mlf_add_int(ptr %a2, ptr inttoptr (i64 9 to ptr))
  br label %join.1502
join.1502:
  %v1514 = phi ptr [ %v1512, %join.1509 ], [ %v1513, %no.1501 ]
  %v1515 = ptrtoint ptr %v1514 to i64
  %v1516 = ashr i64 %v1515, 1
  %v1517 = and i64 %v1515, 1
  %v1518 = icmp ne i64 %v1517, 0
  %v1519 = icmp ult i64 %v1516, %v1482
  %v1520 = and i1 %v1518, %v1519
  br i1 %v1520, label %array.valid.1521, label %array.invalid.1522
array.invalid.1522:
  call void @mlf_bounds_failure()
  unreachable
array.valid.1521:
  %v1523 = getelementptr i64, ptr %v1484, i64 %v1516
  %v1524 = load double, ptr %v1523, align 8, !tbaa !4
  %v1525 = ptrtoint ptr %a2 to i64
  %v1526 = ptrtoint ptr inttoptr (i64 11 to ptr) to i64
  %v1527 = and i64 %v1525, %v1526
  %v1528 = and i64 %v1527, 1
  %v1529 = icmp ne i64 %v1528, 0
  br i1 %v1529, label %yes.1530, label %no.1531
yes.1530:
  %v1533 = sub i64 %v1526, 1
  %v1534 = call { i64, i1 } @llvm.sadd.with.overflow.i64(i64 %v1525, i64 %v1533)
  %v1535 = extractvalue { i64, i1 } %v1534, 0
  %v1536 = extractvalue { i64, i1 } %v1534, 1
  br i1 %v1536, label %yes.1537, label %no.1538
yes.1537:
  %v1540 = call ptr @mlf_add_int(ptr %a2, ptr inttoptr (i64 11 to ptr))
  br label %join.1539
no.1538:
  %v1541 = inttoptr i64 %v1535 to ptr
  br label %join.1539
join.1539:
  %v1542 = phi ptr [ %v1540, %yes.1537 ], [ %v1541, %no.1538 ]
  br label %join.1532
no.1531:
  %v1543 = call ptr @mlf_add_int(ptr %a2, ptr inttoptr (i64 11 to ptr))
  br label %join.1532
join.1532:
  %v1544 = phi ptr [ %v1542, %join.1539 ], [ %v1543, %no.1531 ]
  %v1545 = ptrtoint ptr %v1544 to i64
  %v1546 = ashr i64 %v1545, 1
  %v1547 = and i64 %v1545, 1
  %v1548 = icmp ne i64 %v1547, 0
  %v1549 = icmp ult i64 %v1546, %v1482
  %v1550 = and i1 %v1548, %v1549
  br i1 %v1550, label %array.valid.1551, label %array.invalid.1552
array.invalid.1552:
  call void @mlf_bounds_failure()
  unreachable
array.valid.1551:
  %v1553 = getelementptr i64, ptr %v1484, i64 %v1546
  %v1554 = load double, ptr %v1553, align 8, !tbaa !4
  %v1555 = ptrtoint ptr %a2 to i64
  %v1556 = ptrtoint ptr inttoptr (i64 13 to ptr) to i64
  %v1557 = and i64 %v1555, %v1556
  %v1558 = and i64 %v1557, 1
  %v1559 = icmp ne i64 %v1558, 0
  br i1 %v1559, label %yes.1560, label %no.1561
yes.1560:
  %v1563 = sub i64 %v1556, 1
  %v1564 = call { i64, i1 } @llvm.sadd.with.overflow.i64(i64 %v1555, i64 %v1563)
  %v1565 = extractvalue { i64, i1 } %v1564, 0
  %v1566 = extractvalue { i64, i1 } %v1564, 1
  br i1 %v1566, label %yes.1567, label %no.1568
yes.1567:
  %v1570 = call ptr @mlf_add_int(ptr %a2, ptr inttoptr (i64 13 to ptr))
  br label %join.1569
no.1568:
  %v1571 = inttoptr i64 %v1565 to ptr
  br label %join.1569
join.1569:
  %v1572 = phi ptr [ %v1570, %yes.1567 ], [ %v1571, %no.1568 ]
  br label %join.1562
no.1561:
  %v1573 = call ptr @mlf_add_int(ptr %a2, ptr inttoptr (i64 13 to ptr))
  br label %join.1562
join.1562:
  %v1574 = phi ptr [ %v1572, %join.1569 ], [ %v1573, %no.1561 ]
  %v1575 = ptrtoint ptr %v1574 to i64
  %v1576 = ashr i64 %v1575, 1
  %v1577 = and i64 %v1575, 1
  %v1578 = icmp ne i64 %v1577, 0
  %v1579 = icmp ult i64 %v1576, %v1482
  %v1580 = and i1 %v1578, %v1579
  br i1 %v1580, label %array.valid.1581, label %array.invalid.1582
array.invalid.1582:
  call void @mlf_bounds_failure()
  unreachable
array.valid.1581:
  %v1583 = getelementptr i64, ptr %v1484, i64 %v1576
  %v1584 = load double, ptr %v1583, align 8, !tbaa !4
  %v1585 = ptrtoint ptr %a2 to i64
  %v1586 = ptrtoint ptr inttoptr (i64 15 to ptr) to i64
  %v1587 = and i64 %v1585, %v1586
  %v1588 = and i64 %v1587, 1
  %v1589 = icmp ne i64 %v1588, 0
  br i1 %v1589, label %yes.1590, label %no.1591
yes.1590:
  %v1593 = sub i64 %v1586, 1
  %v1594 = call { i64, i1 } @llvm.sadd.with.overflow.i64(i64 %v1585, i64 %v1593)
  %v1595 = extractvalue { i64, i1 } %v1594, 0
  %v1596 = extractvalue { i64, i1 } %v1594, 1
  br i1 %v1596, label %yes.1597, label %no.1598
yes.1597:
  %v1600 = call ptr @mlf_add_int(ptr %a2, ptr inttoptr (i64 15 to ptr))
  br label %join.1599
no.1598:
  %v1601 = inttoptr i64 %v1595 to ptr
  br label %join.1599
join.1599:
  %v1602 = phi ptr [ %v1600, %yes.1597 ], [ %v1601, %no.1598 ]
  br label %join.1592
no.1591:
  %v1603 = call ptr @mlf_add_int(ptr %a2, ptr inttoptr (i64 15 to ptr))
  br label %join.1592
join.1592:
  %v1604 = phi ptr [ %v1602, %join.1599 ], [ %v1603, %no.1591 ]
  %v1605 = fmul double %v1494, %v1584
  %v1606 = getelementptr i8, ptr %a3, i64 24
  %v1607 = load double, ptr %v1606, align 8, !tbaa !3
  %v1608 = fadd double %v1607, %v1605
  %v1609 = fmul double %v1524, %v1584
  %v1610 = getelementptr i8, ptr %a4, i64 24
  %v1611 = load double, ptr %v1610, align 8, !tbaa !3
  %v1612 = fadd double %v1611, %v1609
  %v1613 = fmul double %v1554, %v1584
  %v1614 = getelementptr i8, ptr %a5, i64 24
  %v1615 = load double, ptr %v1614, align 8, !tbaa !3
  %v1616 = fadd double %v1615, %v1613
  %v1822 = call ptr @mlf.numeric.1.pppddd(ptr %a0, ptr %a1, ptr %v1604, double %v1608, double %v1612, double %v1616)
  ret ptr %v1822
}

define private ptr @mlf.code.1837(ptr %env, ptr %arg) {
entry:
  %v1838 = getelementptr i8, ptr %env, i64 24
  %v1839 = load ptr, ptr %v1838, align 8, !tbaa !3
  %v1840 = getelementptr i8, ptr %env, i64 32
  %v1841 = load ptr, ptr %v1840, align 8, !tbaa !3
  %v1842 = call ptr @mlf_double(double 0x0000000000000000)
  %v1843 = call ptr @mlf_force(ptr %v1841)
  %v1844 = call ptr @mlf_prim2(i64 19, ptr %v1842, ptr %v1843)
  %v1845 = call ptr @mlf_force(ptr %v1839)
  %v1846 = call ptr @mlf_prim2(i64 21, ptr %v1844, ptr %v1845)
  ret ptr %v1846
}

define private ptr @mlf.code.1851(ptr %env, ptr %arg) {
entry:
  %v1852 = call ptr @mlf_prim2(i64 8, ptr inttoptr (i64 1 to ptr), ptr inttoptr (i64 7 to ptr))
  ret ptr %v1852
}

define private ptr @mlf.code.1830(ptr %env, ptr %arg) {
entry:
  %v1831 = getelementptr i8, ptr %env, i64 24
  %v1832 = load ptr, ptr %v1831, align 8, !tbaa !3
  %v1833 = getelementptr i8, ptr %env, i64 32
  %v1834 = load ptr, ptr %v1833, align 8, !tbaa !3
  %v1835 = getelementptr i8, ptr %env, i64 40
  %v1836 = load ptr, ptr %v1835, align 8, !tbaa !3
  %v1847 = call ptr @mlf_env_new(i64 2)
  %v1848 = getelementptr i8, ptr %v1847, i64 24
  store ptr %v1832, ptr %v1848, align 8, !tbaa !3
  %v1849 = getelementptr i8, ptr %v1847, i64 32
  store ptr %v1836, ptr %v1849, align 8, !tbaa !3
  %v1850 = call ptr @mlf_thunk(ptr @mlf.code.1837, ptr %v1847)
  %v1853 = call ptr @mlf_thunk(ptr @mlf.code.1851, ptr null)
  %v1854 = call ptr @mlf_prim3(i64 33, ptr %v1834, ptr %v1853, ptr %v1850)
  ret ptr %v1854
}

define private ptr @mlf.code.1876(ptr %env, ptr %arg) {
entry:
  %v1877 = getelementptr i8, ptr %env, i64 24
  %v1878 = load ptr, ptr %v1877, align 8, !tbaa !3
  %v1879 = getelementptr i8, ptr %env, i64 32
  %v1880 = load ptr, ptr %v1879, align 8, !tbaa !3
  %v1881 = call ptr @mlf_double(double 0x0000000000000000)
  %v1882 = call ptr @mlf_force(ptr %v1880)
  %v1883 = call ptr @mlf_prim2(i64 19, ptr %v1881, ptr %v1882)
  %v1884 = call ptr @mlf_force(ptr %v1878)
  %v1885 = call ptr @mlf_prim2(i64 21, ptr %v1883, ptr %v1884)
  ret ptr %v1885
}

define private ptr @mlf.code.1890(ptr %env, ptr %arg) {
entry:
  %v1891 = call ptr @mlf_prim2(i64 8, ptr inttoptr (i64 1 to ptr), ptr inttoptr (i64 9 to ptr))
  ret ptr %v1891
}

define private ptr @mlf.code.1869(ptr %env, ptr %arg) {
entry:
  %v1870 = getelementptr i8, ptr %env, i64 24
  %v1871 = load ptr, ptr %v1870, align 8, !tbaa !3
  %v1872 = getelementptr i8, ptr %env, i64 32
  %v1873 = load ptr, ptr %v1872, align 8, !tbaa !3
  %v1874 = getelementptr i8, ptr %env, i64 40
  %v1875 = load ptr, ptr %v1874, align 8, !tbaa !3
  %v1886 = call ptr @mlf_env_new(i64 2)
  %v1887 = getelementptr i8, ptr %v1886, i64 24
  store ptr %v1871, ptr %v1887, align 8, !tbaa !3
  %v1888 = getelementptr i8, ptr %v1886, i64 32
  store ptr %v1875, ptr %v1888, align 8, !tbaa !3
  %v1889 = call ptr @mlf_thunk(ptr @mlf.code.1876, ptr %v1886)
  %v1892 = call ptr @mlf_thunk(ptr @mlf.code.1890, ptr null)
  %v1893 = call ptr @mlf_prim3(i64 33, ptr %v1873, ptr %v1892, ptr %v1889)
  ret ptr %v1893
}

define private ptr @mlf.code.1906(ptr %env, ptr %arg) {
entry:
  %v1907 = getelementptr i8, ptr %env, i64 24
  %v1908 = load ptr, ptr %v1907, align 8, !tbaa !3
  %v1909 = getelementptr i8, ptr %env, i64 32
  %v1910 = load ptr, ptr %v1909, align 8, !tbaa !3
  %v1911 = call ptr @mlf_double(double 0x0000000000000000)
  %v1912 = call ptr @mlf_force(ptr %v1910)
  %v1913 = call ptr @mlf_prim2(i64 19, ptr %v1911, ptr %v1912)
  %v1914 = call ptr @mlf_force(ptr %v1908)
  %v1915 = call ptr @mlf_prim2(i64 21, ptr %v1913, ptr %v1914)
  ret ptr %v1915
}

define private ptr @mlf.code.1920(ptr %env, ptr %arg) {
entry:
  %v1921 = call ptr @mlf_prim2(i64 8, ptr inttoptr (i64 1 to ptr), ptr inttoptr (i64 11 to ptr))
  ret ptr %v1921
}

define private ptr @mlf.code.1899(ptr %env, ptr %arg) {
entry:
  %v1900 = getelementptr i8, ptr %env, i64 24
  %v1901 = load ptr, ptr %v1900, align 8, !tbaa !3
  %v1902 = getelementptr i8, ptr %env, i64 32
  %v1903 = load ptr, ptr %v1902, align 8, !tbaa !3
  %v1904 = getelementptr i8, ptr %env, i64 40
  %v1905 = load ptr, ptr %v1904, align 8, !tbaa !3
  %v1916 = call ptr @mlf_env_new(i64 2)
  %v1917 = getelementptr i8, ptr %v1916, i64 24
  store ptr %v1901, ptr %v1917, align 8, !tbaa !3
  %v1918 = getelementptr i8, ptr %v1916, i64 32
  store ptr %v1905, ptr %v1918, align 8, !tbaa !3
  %v1919 = call ptr @mlf_thunk(ptr @mlf.code.1906, ptr %v1916)
  %v1922 = call ptr @mlf_thunk(ptr @mlf.code.1920, ptr null)
  %v1923 = call ptr @mlf_prim3(i64 33, ptr %v1903, ptr %v1922, ptr %v1919)
  ret ptr %v1923
}

define private ptr @mlf.code.1860(ptr %env, ptr %arg) {
entry:
  %v1861 = getelementptr i8, ptr %env, i64 24
  %v1862 = load ptr, ptr %v1861, align 8, !tbaa !3
  %v1863 = getelementptr i8, ptr %env, i64 32
  %v1864 = load ptr, ptr %v1863, align 8, !tbaa !3
  %v1865 = getelementptr i8, ptr %env, i64 40
  %v1866 = load ptr, ptr %v1865, align 8, !tbaa !3
  %v1867 = getelementptr i8, ptr %env, i64 48
  %v1868 = load ptr, ptr %v1867, align 8, !tbaa !3
  %v1894 = call ptr @mlf_env_new(i64 3)
  %v1895 = getelementptr i8, ptr %v1894, i64 24
  store ptr %v1862, ptr %v1895, align 8, !tbaa !3
  %v1896 = getelementptr i8, ptr %v1894, i64 32
  store ptr %v1864, ptr %v1896, align 8, !tbaa !3
  %v1897 = getelementptr i8, ptr %v1894, i64 40
  store ptr %v1866, ptr %v1897, align 8, !tbaa !3
  %v1898 = call ptr @mlf_thunk(ptr @mlf.code.1869, ptr %v1894)
  %v1924 = call ptr @mlf_env_new(i64 3)
  %v1925 = getelementptr i8, ptr %v1924, i64 24
  store ptr %v1862, ptr %v1925, align 8, !tbaa !3
  %v1926 = getelementptr i8, ptr %v1924, i64 32
  store ptr %v1864, ptr %v1926, align 8, !tbaa !3
  %v1927 = getelementptr i8, ptr %v1924, i64 40
  store ptr %v1868, ptr %v1927, align 8, !tbaa !3
  %v1928 = call ptr @mlf_closure(ptr @mlf.code.1899, ptr %v1924)
  %v1929 = call ptr @mlf_prim2(i64 1, ptr %v1898, ptr %v1928)
  ret ptr %v1929
}

define private ptr @mlf.code.1942(ptr %env, ptr %arg) {
entry:
  %v1943 = getelementptr i8, ptr %env, i64 24
  %v1944 = load ptr, ptr %v1943, align 8, !tbaa !3
  %v1945 = call ptr @mlf_force(ptr %v1944)
  %v1946 = call ptr @mlf_prim2(i64 8, ptr %v1945, ptr inttoptr (i64 7 to ptr))
  ret ptr %v1946
}

define private ptr @mlf.code.1937(ptr %env, ptr %arg) {
entry:
  %v1938 = getelementptr i8, ptr %env, i64 24
  %v1939 = load ptr, ptr %v1938, align 8, !tbaa !3
  %v1940 = getelementptr i8, ptr %env, i64 32
  %v1941 = load ptr, ptr %v1940, align 8, !tbaa !3
  %v1947 = call ptr @mlf_env_new(i64 1)
  %v1948 = getelementptr i8, ptr %v1947, i64 24
  store ptr %v1941, ptr %v1948, align 8, !tbaa !3
  %v1949 = call ptr @mlf_thunk(ptr @mlf.code.1942, ptr %v1947)
  %v1950 = call ptr @mlf_prim2(i64 32, ptr %v1939, ptr %v1949)
  ret ptr %v1950
}

define private ptr @mlf.code.1973(ptr %env, ptr %arg) {
entry:
  %v1974 = getelementptr i8, ptr %env, i64 24
  %v1975 = load ptr, ptr %v1974, align 8, !tbaa !3
  %v1976 = call ptr @mlf_force(ptr %v1975)
  %v1977 = call ptr @mlf_prim2(i64 8, ptr %v1976, ptr inttoptr (i64 9 to ptr))
  ret ptr %v1977
}

define private ptr @mlf.code.1968(ptr %env, ptr %arg) {
entry:
  %v1969 = getelementptr i8, ptr %env, i64 24
  %v1970 = load ptr, ptr %v1969, align 8, !tbaa !3
  %v1971 = getelementptr i8, ptr %env, i64 32
  %v1972 = load ptr, ptr %v1971, align 8, !tbaa !3
  %v1978 = call ptr @mlf_env_new(i64 1)
  %v1979 = getelementptr i8, ptr %v1978, i64 24
  store ptr %v1972, ptr %v1979, align 8, !tbaa !3
  %v1980 = call ptr @mlf_thunk(ptr @mlf.code.1973, ptr %v1978)
  %v1981 = call ptr @mlf_prim2(i64 32, ptr %v1970, ptr %v1980)
  ret ptr %v1981
}

define private ptr @mlf.code.2006(ptr %env, ptr %arg) {
entry:
  %v2007 = getelementptr i8, ptr %env, i64 24
  %v2008 = load ptr, ptr %v2007, align 8, !tbaa !3
  %v2009 = call ptr @mlf_force(ptr %v2008)
  %v2010 = call ptr @mlf_prim2(i64 8, ptr %v2009, ptr inttoptr (i64 11 to ptr))
  ret ptr %v2010
}

define private ptr @mlf.code.2001(ptr %env, ptr %arg) {
entry:
  %v2002 = getelementptr i8, ptr %env, i64 24
  %v2003 = load ptr, ptr %v2002, align 8, !tbaa !3
  %v2004 = getelementptr i8, ptr %env, i64 32
  %v2005 = load ptr, ptr %v2004, align 8, !tbaa !3
  %v2011 = call ptr @mlf_env_new(i64 1)
  %v2012 = getelementptr i8, ptr %v2011, i64 24
  store ptr %v2005, ptr %v2012, align 8, !tbaa !3
  %v2013 = call ptr @mlf_thunk(ptr @mlf.code.2006, ptr %v2011)
  %v2014 = call ptr @mlf_prim2(i64 32, ptr %v2003, ptr %v2013)
  ret ptr %v2014
}

define private ptr @mlf.code.2041(ptr %env, ptr %arg) {
entry:
  %v2042 = getelementptr i8, ptr %env, i64 24
  %v2043 = load ptr, ptr %v2042, align 8, !tbaa !3
  %v2044 = call ptr @mlf_force(ptr %v2043)
  %v2045 = call ptr @mlf_prim2(i64 8, ptr %v2044, ptr inttoptr (i64 13 to ptr))
  ret ptr %v2045
}

define private ptr @mlf.code.2036(ptr %env, ptr %arg) {
entry:
  %v2037 = getelementptr i8, ptr %env, i64 24
  %v2038 = load ptr, ptr %v2037, align 8, !tbaa !3
  %v2039 = getelementptr i8, ptr %env, i64 32
  %v2040 = load ptr, ptr %v2039, align 8, !tbaa !3
  %v2046 = call ptr @mlf_env_new(i64 1)
  %v2047 = getelementptr i8, ptr %v2046, i64 24
  store ptr %v2040, ptr %v2047, align 8, !tbaa !3
  %v2048 = call ptr @mlf_thunk(ptr @mlf.code.2041, ptr %v2046)
  %v2049 = call ptr @mlf_prim2(i64 32, ptr %v2038, ptr %v2048)
  ret ptr %v2049
}

define private ptr @mlf.code.2075(ptr %env, ptr %arg) {
entry:
  %v2076 = getelementptr i8, ptr %env, i64 24
  %v2077 = load ptr, ptr %v2076, align 8, !tbaa !3
  %v2078 = getelementptr i8, ptr %env, i64 32
  %v2079 = load ptr, ptr %v2078, align 8, !tbaa !3
  %v2080 = getelementptr i8, ptr %env, i64 40
  %v2081 = load ptr, ptr %v2080, align 8, !tbaa !3
  %v2082 = call ptr @mlf_force(ptr %v2077)
  %v2083 = call ptr @mlf_force(ptr %v2079)
  %v2084 = call ptr @mlf_force(ptr %v2081)
  %v2085 = call ptr @mlf_prim2(i64 20, ptr %v2083, ptr %v2084)
  %v2086 = call ptr @mlf_prim2(i64 18, ptr %v2082, ptr %v2085)
  ret ptr %v2086
}

define private ptr @mlf.code.2092(ptr %env, ptr %arg) {
entry:
  %v2093 = getelementptr i8, ptr %env, i64 24
  %v2094 = load ptr, ptr %v2093, align 8, !tbaa !3
  %v2095 = getelementptr i8, ptr %env, i64 32
  %v2096 = load ptr, ptr %v2095, align 8, !tbaa !3
  %v2097 = getelementptr i8, ptr %env, i64 40
  %v2098 = load ptr, ptr %v2097, align 8, !tbaa !3
  %v2099 = call ptr @mlf_force(ptr %v2094)
  %v2100 = call ptr @mlf_force(ptr %v2096)
  %v2101 = call ptr @mlf_force(ptr %v2098)
  %v2102 = call ptr @mlf_prim2(i64 20, ptr %v2100, ptr %v2101)
  %v2103 = call ptr @mlf_prim2(i64 18, ptr %v2099, ptr %v2102)
  ret ptr %v2103
}

define private ptr @mlf.code.2109(ptr %env, ptr %arg) {
entry:
  %v2110 = getelementptr i8, ptr %env, i64 24
  %v2111 = load ptr, ptr %v2110, align 8, !tbaa !3
  %v2112 = getelementptr i8, ptr %env, i64 32
  %v2113 = load ptr, ptr %v2112, align 8, !tbaa !3
  %v2114 = getelementptr i8, ptr %env, i64 40
  %v2115 = load ptr, ptr %v2114, align 8, !tbaa !3
  %v2116 = call ptr @mlf_force(ptr %v2111)
  %v2117 = call ptr @mlf_force(ptr %v2113)
  %v2118 = call ptr @mlf_force(ptr %v2115)
  %v2119 = call ptr @mlf_prim2(i64 20, ptr %v2117, ptr %v2118)
  %v2120 = call ptr @mlf_prim2(i64 18, ptr %v2116, ptr %v2119)
  ret ptr %v2120
}

define private ptr @mlf.code.2054(ptr %env, ptr %arg) {
entry:
  %v2055 = getelementptr i8, ptr %env, i64 24
  %v2056 = load ptr, ptr %v2055, align 8, !tbaa !3
  %v2057 = getelementptr i8, ptr %env, i64 32
  %v2058 = load ptr, ptr %v2057, align 8, !tbaa !3
  %v2059 = getelementptr i8, ptr %env, i64 40
  %v2060 = load ptr, ptr %v2059, align 8, !tbaa !3
  %v2061 = getelementptr i8, ptr %env, i64 48
  %v2062 = load ptr, ptr %v2061, align 8, !tbaa !3
  %v2063 = getelementptr i8, ptr %env, i64 56
  %v2064 = load ptr, ptr %v2063, align 8, !tbaa !3
  %v2065 = getelementptr i8, ptr %env, i64 64
  %v2066 = load ptr, ptr %v2065, align 8, !tbaa !3
  %v2067 = getelementptr i8, ptr %env, i64 72
  %v2068 = load ptr, ptr %v2067, align 8, !tbaa !3
  %v2069 = getelementptr i8, ptr %env, i64 80
  %v2070 = load ptr, ptr %v2069, align 8, !tbaa !3
  %v2071 = getelementptr i8, ptr %env, i64 88
  %v2072 = load ptr, ptr %v2071, align 8, !tbaa !3
  %v2073 = call ptr @mlf_force(ptr %v2060)
  %v2074 = call ptr @mlf_prim2(i64 8, ptr %v2073, ptr inttoptr (i64 15 to ptr))
  %v2087 = call ptr @mlf_env_new(i64 3)
  %v2088 = getelementptr i8, ptr %v2087, i64 24
  store ptr %v2062, ptr %v2088, align 8, !tbaa !3
  %v2089 = getelementptr i8, ptr %v2087, i64 32
  store ptr %v2068, ptr %v2089, align 8, !tbaa !3
  %v2090 = getelementptr i8, ptr %v2087, i64 40
  store ptr %arg, ptr %v2090, align 8, !tbaa !3
  %v2091 = call ptr @mlf_thunk(ptr @mlf.code.2075, ptr %v2087)
  %v2104 = call ptr @mlf_env_new(i64 3)
  %v2105 = getelementptr i8, ptr %v2104, i64 24
  store ptr %v2064, ptr %v2105, align 8, !tbaa !3
  %v2106 = getelementptr i8, ptr %v2104, i64 32
  store ptr %v2070, ptr %v2106, align 8, !tbaa !3
  %v2107 = getelementptr i8, ptr %v2104, i64 40
  store ptr %arg, ptr %v2107, align 8, !tbaa !3
  %v2108 = call ptr @mlf_thunk(ptr @mlf.code.2092, ptr %v2104)
  %v2121 = call ptr @mlf_env_new(i64 3)
  %v2122 = getelementptr i8, ptr %v2121, i64 24
  store ptr %v2066, ptr %v2122, align 8, !tbaa !3
  %v2123 = getelementptr i8, ptr %v2121, i64 32
  store ptr %v2072, ptr %v2123, align 8, !tbaa !3
  %v2124 = getelementptr i8, ptr %v2121, i64 40
  store ptr %arg, ptr %v2124, align 8, !tbaa !3
  %v2125 = call ptr @mlf_thunk(ptr @mlf.code.2109, ptr %v2121)
  %v2126 = call ptr @mlf_env_new(i64 6)
  %v2127 = getelementptr i8, ptr %v2126, i64 24
  store ptr %v2056, ptr %v2127, align 8, !tbaa !3
  %v2128 = getelementptr i8, ptr %v2126, i64 32
  store ptr %v2058, ptr %v2128, align 8, !tbaa !3
  %v2129 = getelementptr i8, ptr %v2126, i64 40
  store ptr %v2074, ptr %v2129, align 8, !tbaa !3
  %v2130 = getelementptr i8, ptr %v2126, i64 48
  store ptr %v2091, ptr %v2130, align 8, !tbaa !3
  %v2131 = getelementptr i8, ptr %v2126, i64 56
  store ptr %v2108, ptr %v2131, align 8, !tbaa !3
  %v2132 = getelementptr i8, ptr %v2126, i64 64
  store ptr %v2125, ptr %v2132, align 8, !tbaa !3
  %v2133 = call ptr @mlf_native_io(ptr @mlf.numeric.entry.1367, ptr %v2126)
  ret ptr %v2133
}

define private ptr @mlf.code.2019(ptr %env, ptr %arg) {
entry:
  %v2020 = getelementptr i8, ptr %env, i64 24
  %v2021 = load ptr, ptr %v2020, align 8, !tbaa !3
  %v2022 = getelementptr i8, ptr %env, i64 32
  %v2023 = load ptr, ptr %v2022, align 8, !tbaa !3
  %v2024 = getelementptr i8, ptr %env, i64 40
  %v2025 = load ptr, ptr %v2024, align 8, !tbaa !3
  %v2026 = getelementptr i8, ptr %env, i64 48
  %v2027 = load ptr, ptr %v2026, align 8, !tbaa !3
  %v2028 = getelementptr i8, ptr %env, i64 56
  %v2029 = load ptr, ptr %v2028, align 8, !tbaa !3
  %v2030 = getelementptr i8, ptr %env, i64 64
  %v2031 = load ptr, ptr %v2030, align 8, !tbaa !3
  %v2032 = getelementptr i8, ptr %env, i64 72
  %v2033 = load ptr, ptr %v2032, align 8, !tbaa !3
  %v2034 = getelementptr i8, ptr %env, i64 80
  %v2035 = load ptr, ptr %v2034, align 8, !tbaa !3
  %v2050 = call ptr @mlf_env_new(i64 2)
  %v2051 = getelementptr i8, ptr %v2050, i64 24
  store ptr %v2023, ptr %v2051, align 8, !tbaa !3
  %v2052 = getelementptr i8, ptr %v2050, i64 32
  store ptr %v2025, ptr %v2052, align 8, !tbaa !3
  %v2053 = call ptr @mlf_thunk(ptr @mlf.code.2036, ptr %v2050)
  %v2134 = call ptr @mlf_env_new(i64 9)
  %v2135 = getelementptr i8, ptr %v2134, i64 24
  store ptr %v2021, ptr %v2135, align 8, !tbaa !3
  %v2136 = getelementptr i8, ptr %v2134, i64 32
  store ptr %v2023, ptr %v2136, align 8, !tbaa !3
  %v2137 = getelementptr i8, ptr %v2134, i64 40
  store ptr %v2025, ptr %v2137, align 8, !tbaa !3
  %v2138 = getelementptr i8, ptr %v2134, i64 48
  store ptr %v2027, ptr %v2138, align 8, !tbaa !3
  %v2139 = getelementptr i8, ptr %v2134, i64 56
  store ptr %v2029, ptr %v2139, align 8, !tbaa !3
  %v2140 = getelementptr i8, ptr %v2134, i64 64
  store ptr %v2031, ptr %v2140, align 8, !tbaa !3
  %v2141 = getelementptr i8, ptr %v2134, i64 72
  store ptr %v2033, ptr %v2141, align 8, !tbaa !3
  %v2142 = getelementptr i8, ptr %v2134, i64 80
  store ptr %v2035, ptr %v2142, align 8, !tbaa !3
  %v2143 = getelementptr i8, ptr %v2134, i64 88
  store ptr %arg, ptr %v2143, align 8, !tbaa !3
  %v2144 = call ptr @mlf_closure(ptr @mlf.code.2054, ptr %v2134)
  %v2145 = call ptr @mlf_prim2(i64 1, ptr %v2053, ptr %v2144)
  ret ptr %v2145
}

define private ptr @mlf.code.1986(ptr %env, ptr %arg) {
entry:
  %v1987 = getelementptr i8, ptr %env, i64 24
  %v1988 = load ptr, ptr %v1987, align 8, !tbaa !3
  %v1989 = getelementptr i8, ptr %env, i64 32
  %v1990 = load ptr, ptr %v1989, align 8, !tbaa !3
  %v1991 = getelementptr i8, ptr %env, i64 40
  %v1992 = load ptr, ptr %v1991, align 8, !tbaa !3
  %v1993 = getelementptr i8, ptr %env, i64 48
  %v1994 = load ptr, ptr %v1993, align 8, !tbaa !3
  %v1995 = getelementptr i8, ptr %env, i64 56
  %v1996 = load ptr, ptr %v1995, align 8, !tbaa !3
  %v1997 = getelementptr i8, ptr %env, i64 64
  %v1998 = load ptr, ptr %v1997, align 8, !tbaa !3
  %v1999 = getelementptr i8, ptr %env, i64 72
  %v2000 = load ptr, ptr %v1999, align 8, !tbaa !3
  %v2015 = call ptr @mlf_env_new(i64 2)
  %v2016 = getelementptr i8, ptr %v2015, i64 24
  store ptr %v1990, ptr %v2016, align 8, !tbaa !3
  %v2017 = getelementptr i8, ptr %v2015, i64 32
  store ptr %v1992, ptr %v2017, align 8, !tbaa !3
  %v2018 = call ptr @mlf_thunk(ptr @mlf.code.2001, ptr %v2015)
  %v2146 = call ptr @mlf_env_new(i64 8)
  %v2147 = getelementptr i8, ptr %v2146, i64 24
  store ptr %v1988, ptr %v2147, align 8, !tbaa !3
  %v2148 = getelementptr i8, ptr %v2146, i64 32
  store ptr %v1990, ptr %v2148, align 8, !tbaa !3
  %v2149 = getelementptr i8, ptr %v2146, i64 40
  store ptr %v1992, ptr %v2149, align 8, !tbaa !3
  %v2150 = getelementptr i8, ptr %v2146, i64 48
  store ptr %v1994, ptr %v2150, align 8, !tbaa !3
  %v2151 = getelementptr i8, ptr %v2146, i64 56
  store ptr %v1996, ptr %v2151, align 8, !tbaa !3
  %v2152 = getelementptr i8, ptr %v2146, i64 64
  store ptr %v1998, ptr %v2152, align 8, !tbaa !3
  %v2153 = getelementptr i8, ptr %v2146, i64 72
  store ptr %v2000, ptr %v2153, align 8, !tbaa !3
  %v2154 = getelementptr i8, ptr %v2146, i64 80
  store ptr %arg, ptr %v2154, align 8, !tbaa !3
  %v2155 = call ptr @mlf_closure(ptr @mlf.code.2019, ptr %v2146)
  %v2156 = call ptr @mlf_prim2(i64 1, ptr %v2018, ptr %v2155)
  ret ptr %v2156
}

define private ptr @mlf.code.1955(ptr %env, ptr %arg) {
entry:
  %v1956 = getelementptr i8, ptr %env, i64 24
  %v1957 = load ptr, ptr %v1956, align 8, !tbaa !3
  %v1958 = getelementptr i8, ptr %env, i64 32
  %v1959 = load ptr, ptr %v1958, align 8, !tbaa !3
  %v1960 = getelementptr i8, ptr %env, i64 40
  %v1961 = load ptr, ptr %v1960, align 8, !tbaa !3
  %v1962 = getelementptr i8, ptr %env, i64 48
  %v1963 = load ptr, ptr %v1962, align 8, !tbaa !3
  %v1964 = getelementptr i8, ptr %env, i64 56
  %v1965 = load ptr, ptr %v1964, align 8, !tbaa !3
  %v1966 = getelementptr i8, ptr %env, i64 64
  %v1967 = load ptr, ptr %v1966, align 8, !tbaa !3
  %v1982 = call ptr @mlf_env_new(i64 2)
  %v1983 = getelementptr i8, ptr %v1982, i64 24
  store ptr %v1959, ptr %v1983, align 8, !tbaa !3
  %v1984 = getelementptr i8, ptr %v1982, i64 32
  store ptr %v1961, ptr %v1984, align 8, !tbaa !3
  %v1985 = call ptr @mlf_thunk(ptr @mlf.code.1968, ptr %v1982)
  %v2157 = call ptr @mlf_env_new(i64 7)
  %v2158 = getelementptr i8, ptr %v2157, i64 24
  store ptr %v1957, ptr %v2158, align 8, !tbaa !3
  %v2159 = getelementptr i8, ptr %v2157, i64 32
  store ptr %v1959, ptr %v2159, align 8, !tbaa !3
  %v2160 = getelementptr i8, ptr %v2157, i64 40
  store ptr %v1961, ptr %v2160, align 8, !tbaa !3
  %v2161 = getelementptr i8, ptr %v2157, i64 48
  store ptr %v1963, ptr %v2161, align 8, !tbaa !3
  %v2162 = getelementptr i8, ptr %v2157, i64 56
  store ptr %v1965, ptr %v2162, align 8, !tbaa !3
  %v2163 = getelementptr i8, ptr %v2157, i64 64
  store ptr %v1967, ptr %v2163, align 8, !tbaa !3
  %v2164 = getelementptr i8, ptr %v2157, i64 72
  store ptr %arg, ptr %v2164, align 8, !tbaa !3
  %v2165 = call ptr @mlf_closure(ptr @mlf.code.1986, ptr %v2157)
  %v2166 = call ptr @mlf_prim2(i64 1, ptr %v1985, ptr %v2165)
  ret ptr %v2166
}

define private ptr @mlf.worker.1(ptr %a0, ptr %a1, ptr %a2, ptr %a3, ptr %a4, ptr %a5) {
entry:
  %v1825 = call ptr @mlf_prim2(i64 10, ptr %a2, ptr inttoptr (i64 71 to ptr))
  %v1826 = icmp eq ptr %v1825, inttoptr (i64 6 to ptr)
  br i1 %v1826, label %yes.1827, label %no.1828
yes.1827:
  %v1855 = call ptr @mlf_env_new(i64 3)
  %v1856 = getelementptr i8, ptr %v1855, i64 24
  store ptr %a0, ptr %v1856, align 8, !tbaa !3
  %v1857 = getelementptr i8, ptr %v1855, i64 32
  store ptr %a1, ptr %v1857, align 8, !tbaa !3
  %v1858 = getelementptr i8, ptr %v1855, i64 40
  store ptr %a3, ptr %v1858, align 8, !tbaa !3
  %v1859 = call ptr @mlf_thunk(ptr @mlf.code.1830, ptr %v1855)
  %v1930 = call ptr @mlf_env_new(i64 4)
  %v1931 = getelementptr i8, ptr %v1930, i64 24
  store ptr %a0, ptr %v1931, align 8, !tbaa !3
  %v1932 = getelementptr i8, ptr %v1930, i64 32
  store ptr %a1, ptr %v1932, align 8, !tbaa !3
  %v1933 = getelementptr i8, ptr %v1930, i64 40
  store ptr %a4, ptr %v1933, align 8, !tbaa !3
  %v1934 = getelementptr i8, ptr %v1930, i64 48
  store ptr %a5, ptr %v1934, align 8, !tbaa !3
  %v1935 = call ptr @mlf_closure(ptr @mlf.code.1860, ptr %v1930)
  %v1936 = call ptr @mlf_prim2(i64 1, ptr %v1859, ptr %v1935)
  br label %join.1829
no.1828:
  %v1951 = call ptr @mlf_env_new(i64 2)
  %v1952 = getelementptr i8, ptr %v1951, i64 24
  store ptr %a1, ptr %v1952, align 8, !tbaa !3
  %v1953 = getelementptr i8, ptr %v1951, i64 32
  store ptr %a2, ptr %v1953, align 8, !tbaa !3
  %v1954 = call ptr @mlf_thunk(ptr @mlf.code.1937, ptr %v1951)
  %v2167 = call ptr @mlf_env_new(i64 6)
  %v2168 = getelementptr i8, ptr %v2167, i64 24
  store ptr %a0, ptr %v2168, align 8, !tbaa !3
  %v2169 = getelementptr i8, ptr %v2167, i64 32
  store ptr %a1, ptr %v2169, align 8, !tbaa !3
  %v2170 = getelementptr i8, ptr %v2167, i64 40
  store ptr %a2, ptr %v2170, align 8, !tbaa !3
  %v2171 = getelementptr i8, ptr %v2167, i64 48
  store ptr %a3, ptr %v2171, align 8, !tbaa !3
  %v2172 = getelementptr i8, ptr %v2167, i64 56
  store ptr %a4, ptr %v2172, align 8, !tbaa !3
  %v2173 = getelementptr i8, ptr %v2167, i64 64
  store ptr %a5, ptr %v2173, align 8, !tbaa !3
  %v2174 = call ptr @mlf_closure(ptr @mlf.code.1955, ptr %v2167)
  %v2175 = call ptr @mlf_prim2(i64 1, ptr %v1954, ptr %v2174)
  br label %join.1829
join.1829:
  %v2176 = phi ptr [ %v1936, %yes.1827 ], [ %v2175, %no.1828 ]
  ret ptr %v2176
}

define private ptr @mlf.numeric.entry.1367(ptr %env, ptr %arg) {
entry:
  %v1368 = getelementptr i8, ptr %env, i64 24
  %v1369 = load ptr, ptr %v1368, align 8, !tbaa !3
  %v1370 = getelementptr i8, ptr %env, i64 32
  %v1371 = load ptr, ptr %v1370, align 8, !tbaa !3
  %v1372 = getelementptr i8, ptr %env, i64 40
  %v1373 = load ptr, ptr %v1372, align 8, !tbaa !3
  %v1374 = getelementptr i8, ptr %env, i64 48
  %v1375 = load ptr, ptr %v1374, align 8, !tbaa !3
  %v1376 = getelementptr i8, ptr %env, i64 56
  %v1377 = load ptr, ptr %v1376, align 8, !tbaa !3
  %v1378 = getelementptr i8, ptr %env, i64 64
  %v1379 = load ptr, ptr %v1378, align 8, !tbaa !3
  %v1380 = call ptr @mlf_peek(ptr %v1369)
  %v1381 = call ptr @mlf_peek(ptr %v1371)
  %v1382 = call ptr @mlf_peek(ptr %v1373)
  %v1383 = call ptr @mlf_peek(ptr %v1375)
  %v1384 = call ptr @mlf_peek(ptr %v1377)
  %v1385 = call ptr @mlf_peek(ptr %v1379)
  %v1386 = icmp ne ptr %v1380, null
  %v1387 = icmp ne ptr %v1381, null
  %v1388 = icmp ne ptr %v1382, null
  %v1389 = icmp ne ptr %v1383, null
  %v1390 = icmp ne ptr %v1384, null
  %v1391 = icmp ne ptr %v1385, null
  %v1392 = and i1 true, %v1386
  %v1393 = and i1 %v1392, %v1387
  %v1394 = and i1 %v1393, %v1388
  %v1395 = and i1 %v1394, %v1389
  %v1396 = and i1 %v1395, %v1390
  %v1397 = and i1 %v1396, %v1391
  br i1 %v1397, label %yes.1398, label %no.1399
yes.1398:
  %v1823 = call ptr @mlf.numeric.1(ptr %v1380, ptr %v1381, ptr %v1382, ptr %v1383, ptr %v1384, ptr %v1385)
  %v1824 = call ptr @mlf_prim1(i64 0, ptr %v1823)
  br label %join.1400
no.1399:
  %v2177 = call ptr @mlf_force(ptr %v1373)
  %v2178 = call ptr @mlf.worker.1(ptr %v1369, ptr %v1371, ptr %v2177, ptr %v1375, ptr %v1377, ptr %v1379)
  br label %join.1400
join.1400:
  %v2179 = phi ptr [ %v1824, %yes.1398 ], [ %v2178, %no.1399 ]
  ret ptr %v2179
}

define private ptr @mlf.code.1362(ptr %env, ptr %arg) {
entry:
  %v1363 = getelementptr i8, ptr %env, i64 24
  %v1364 = load ptr, ptr %v1363, align 8, !tbaa !3
  %v1365 = getelementptr i8, ptr %env, i64 32
  %v1366 = load ptr, ptr %v1365, align 8, !tbaa !3
  %v2180 = call ptr @mlf_double(double 0x0000000000000000)
  %v2181 = call ptr @mlf_double(double 0x0000000000000000)
  %v2182 = call ptr @mlf_double(double 0x0000000000000000)
  %v2183 = call ptr @mlf_env_new(i64 6)
  %v2184 = getelementptr i8, ptr %v2183, i64 24
  store ptr %v1364, ptr %v2184, align 8, !tbaa !3
  %v2185 = getelementptr i8, ptr %v2183, i64 32
  store ptr %v1366, ptr %v2185, align 8, !tbaa !3
  %v2186 = getelementptr i8, ptr %v2183, i64 40
  store ptr inttoptr (i64 1 to ptr), ptr %v2186, align 8, !tbaa !3
  %v2187 = getelementptr i8, ptr %v2183, i64 48
  store ptr %v2180, ptr %v2187, align 8, !tbaa !3
  %v2188 = getelementptr i8, ptr %v2183, i64 56
  store ptr %v2181, ptr %v2188, align 8, !tbaa !3
  %v2189 = getelementptr i8, ptr %v2183, i64 64
  store ptr %v2182, ptr %v2189, align 8, !tbaa !3
  %v2190 = call ptr @mlf_native_io(ptr @mlf.numeric.entry.1367, ptr %v2183)
  ret ptr %v2190
}

define private ptr @mlf.numeric.16.pppd(ptr %a0, ptr %a1, ptr %a2, double %a3) alwaysinline {
entry:
  %v2391 = ptrtoint ptr %a2 to i64
  %v2392 = ptrtoint ptr inttoptr (i64 71 to ptr) to i64
  %v2393 = and i64 %v2391, %v2392
  %v2394 = and i64 %v2393, 1
  %v2395 = icmp ne i64 %v2394, 0
  br i1 %v2395, label %yes.2396, label %no.2397
yes.2396:
  %v2399 = icmp eq i64 %v2391, %v2392
  %v2400 = select i1 %v2399, ptr inttoptr (i64 6 to ptr), ptr inttoptr (i64 2 to ptr)
  br label %join.2398
no.2397:
  %v2401 = call ptr @mlf_eq_int(ptr %a2, ptr inttoptr (i64 71 to ptr))
  br label %join.2398
join.2398:
  %v2402 = phi ptr [ %v2400, %yes.2396 ], [ %v2401, %no.2397 ]
  %v2403 = icmp eq ptr %v2402, inttoptr (i64 6 to ptr)
  br i1 %v2403, label %tail.yes.2404, label %tail.no.2405
tail.yes.2404:
  %v2406 = call ptr @mlf_double(double %a3)
  ret ptr %v2406
tail.no.2405:
  %v2407 = getelementptr i8, ptr %a0, i64 24
  %v2408 = load i64, ptr %v2407, align 8, !tbaa !3
  %v2409 = getelementptr i8, ptr %a0, i64 32
  %v2410 = load ptr, ptr %v2409, align 8, !tbaa !3
  %v2411 = ptrtoint ptr %a1 to i64
  %v2412 = ashr i64 %v2411, 1
  %v2413 = and i64 %v2411, 1
  %v2414 = icmp ne i64 %v2413, 0
  %v2415 = icmp ult i64 %v2412, %v2408
  %v2416 = and i1 %v2414, %v2415
  br i1 %v2416, label %array.valid.2417, label %array.invalid.2418
array.invalid.2418:
  call void @mlf_bounds_failure()
  unreachable
array.valid.2417:
  %v2419 = getelementptr i64, ptr %v2410, i64 %v2412
  %v2420 = load double, ptr %v2419, align 8, !tbaa !4
  %v2421 = ptrtoint ptr %a1 to i64
  %v2422 = ptrtoint ptr inttoptr (i64 3 to ptr) to i64
  %v2423 = sub i64 %v2422, 1
  %v2424 = add nsw i64 %v2421, %v2423
  %v2425 = inttoptr i64 %v2424 to ptr
  %v2426 = ptrtoint ptr %v2425 to i64
  %v2427 = ashr i64 %v2426, 1
  %v2428 = and i64 %v2426, 1
  %v2429 = icmp ne i64 %v2428, 0
  %v2430 = icmp ult i64 %v2427, %v2408
  %v2431 = and i1 %v2429, %v2430
  br i1 %v2431, label %array.valid.2432, label %array.invalid.2433
array.invalid.2433:
  call void @mlf_bounds_failure()
  unreachable
array.valid.2432:
  %v2434 = getelementptr i64, ptr %v2410, i64 %v2427
  %v2435 = load double, ptr %v2434, align 8, !tbaa !4
  %v2436 = ptrtoint ptr %a1 to i64
  %v2437 = ptrtoint ptr inttoptr (i64 5 to ptr) to i64
  %v2438 = sub i64 %v2437, 1
  %v2439 = add nsw i64 %v2436, %v2438
  %v2440 = inttoptr i64 %v2439 to ptr
  %v2441 = ptrtoint ptr %v2440 to i64
  %v2442 = ashr i64 %v2441, 1
  %v2443 = and i64 %v2441, 1
  %v2444 = icmp ne i64 %v2443, 0
  %v2445 = icmp ult i64 %v2442, %v2408
  %v2446 = and i1 %v2444, %v2445
  br i1 %v2446, label %array.valid.2447, label %array.invalid.2448
array.invalid.2448:
  call void @mlf_bounds_failure()
  unreachable
array.valid.2447:
  %v2449 = getelementptr i64, ptr %v2410, i64 %v2442
  %v2450 = load double, ptr %v2449, align 8, !tbaa !4
  %v2451 = ptrtoint ptr %a1 to i64
  %v2452 = ptrtoint ptr inttoptr (i64 13 to ptr) to i64
  %v2453 = sub i64 %v2452, 1
  %v2454 = add nsw i64 %v2451, %v2453
  %v2455 = inttoptr i64 %v2454 to ptr
  %v2456 = ptrtoint ptr %v2455 to i64
  %v2457 = ashr i64 %v2456, 1
  %v2458 = and i64 %v2456, 1
  %v2459 = icmp ne i64 %v2458, 0
  %v2460 = icmp ult i64 %v2457, %v2408
  %v2461 = and i1 %v2459, %v2460
  br i1 %v2461, label %array.valid.2462, label %array.invalid.2463
array.invalid.2463:
  call void @mlf_bounds_failure()
  unreachable
array.valid.2462:
  %v2464 = getelementptr i64, ptr %v2410, i64 %v2457
  %v2465 = load double, ptr %v2464, align 8, !tbaa !4
  %v2466 = ptrtoint ptr %a2 to i64
  %v2467 = ashr i64 %v2466, 1
  %v2468 = and i64 %v2466, 1
  %v2469 = icmp ne i64 %v2468, 0
  %v2470 = icmp ult i64 %v2467, %v2408
  %v2471 = and i1 %v2469, %v2470
  br i1 %v2471, label %array.valid.2472, label %array.invalid.2473
array.invalid.2473:
  call void @mlf_bounds_failure()
  unreachable
array.valid.2472:
  %v2474 = getelementptr i64, ptr %v2410, i64 %v2467
  %v2475 = load double, ptr %v2474, align 8, !tbaa !4
  %v2476 = ptrtoint ptr %a2 to i64
  %v2477 = ptrtoint ptr inttoptr (i64 3 to ptr) to i64
  %v2478 = sub i64 %v2477, 1
  %v2479 = add nsw i64 %v2476, %v2478
  %v2480 = inttoptr i64 %v2479 to ptr
  %v2481 = ptrtoint ptr %v2480 to i64
  %v2482 = ashr i64 %v2481, 1
  %v2483 = and i64 %v2481, 1
  %v2484 = icmp ne i64 %v2483, 0
  %v2485 = icmp ult i64 %v2482, %v2408
  %v2486 = and i1 %v2484, %v2485
  br i1 %v2486, label %array.valid.2487, label %array.invalid.2488
array.invalid.2488:
  call void @mlf_bounds_failure()
  unreachable
array.valid.2487:
  %v2489 = getelementptr i64, ptr %v2410, i64 %v2482
  %v2490 = load double, ptr %v2489, align 8, !tbaa !4
  %v2491 = ptrtoint ptr %a2 to i64
  %v2492 = ptrtoint ptr inttoptr (i64 5 to ptr) to i64
  %v2493 = sub i64 %v2492, 1
  %v2494 = add nsw i64 %v2491, %v2493
  %v2495 = inttoptr i64 %v2494 to ptr
  %v2496 = ptrtoint ptr %v2495 to i64
  %v2497 = ashr i64 %v2496, 1
  %v2498 = and i64 %v2496, 1
  %v2499 = icmp ne i64 %v2498, 0
  %v2500 = icmp ult i64 %v2497, %v2408
  %v2501 = and i1 %v2499, %v2500
  br i1 %v2501, label %array.valid.2502, label %array.invalid.2503
array.invalid.2503:
  call void @mlf_bounds_failure()
  unreachable
array.valid.2502:
  %v2504 = getelementptr i64, ptr %v2410, i64 %v2497
  %v2505 = load double, ptr %v2504, align 8, !tbaa !4
  %v2506 = ptrtoint ptr %a2 to i64
  %v2507 = ptrtoint ptr inttoptr (i64 13 to ptr) to i64
  %v2508 = sub i64 %v2507, 1
  %v2509 = add nsw i64 %v2506, %v2508
  %v2510 = inttoptr i64 %v2509 to ptr
  %v2511 = ptrtoint ptr %v2510 to i64
  %v2512 = ashr i64 %v2511, 1
  %v2513 = and i64 %v2511, 1
  %v2514 = icmp ne i64 %v2513, 0
  %v2515 = icmp ult i64 %v2512, %v2408
  %v2516 = and i1 %v2514, %v2515
  br i1 %v2516, label %array.valid.2517, label %array.invalid.2518
array.invalid.2518:
  call void @mlf_bounds_failure()
  unreachable
array.valid.2517:
  %v2519 = getelementptr i64, ptr %v2410, i64 %v2512
  %v2520 = load double, ptr %v2519, align 8, !tbaa !4
  %v2521 = fsub double %v2420, %v2475
  %v2522 = fsub double %v2435, %v2490
  %v2523 = fsub double %v2450, %v2505
  %v2524 = fmul double %v2521, %v2521
  %v2525 = fmul double %v2522, %v2522
  %v2526 = fadd double %v2524, %v2525
  %v2527 = fmul double %v2523, %v2523
  %v2528 = fadd double %v2526, %v2527
  %v2529 = call double @llvm.sqrt.f64(double %v2528)
  %v2530 = ptrtoint ptr %a2 to i64
  %v2531 = ptrtoint ptr inttoptr (i64 15 to ptr) to i64
  %v2532 = sub i64 %v2531, 1
  %v2533 = add nsw i64 %v2530, %v2532
  %v2534 = inttoptr i64 %v2533 to ptr
  %v2535 = fmul double %v2465, %v2520
  %v2536 = fdiv double %v2535, %v2529
  %v2537 = fsub double %a3, %v2536
  %v2538 = musttail call ptr @mlf.numeric.16.pppd(ptr %a0, ptr %a1, ptr %v2534, double %v2537)
  ret ptr %v2538
}

define private ptr @mlf.numeric.33(ptr %a0, ptr %a1, ptr %a2) alwaysinline {
entry:
  %v2222 = ptrtoint ptr %a1 to i64
  %v2223 = ptrtoint ptr inttoptr (i64 71 to ptr) to i64
  %v2224 = and i64 %v2222, %v2223
  %v2225 = and i64 %v2224, 1
  %v2226 = icmp ne i64 %v2225, 0
  br i1 %v2226, label %yes.2227, label %no.2228
yes.2227:
  %v2230 = icmp eq i64 %v2222, %v2223
  %v2231 = select i1 %v2230, ptr inttoptr (i64 6 to ptr), ptr inttoptr (i64 2 to ptr)
  br label %join.2229
no.2228:
  %v2232 = call ptr @mlf_eq_int(ptr %a1, ptr inttoptr (i64 71 to ptr))
  br label %join.2229
join.2229:
  %v2233 = phi ptr [ %v2231, %yes.2227 ], [ %v2232, %no.2228 ]
  %v2234 = icmp eq ptr %v2233, inttoptr (i64 6 to ptr)
  br i1 %v2234, label %tail.yes.2235, label %tail.no.2236
tail.yes.2235:
  ret ptr %a2
tail.no.2236:
  %v2237 = ptrtoint ptr %a1 to i64
  %v2238 = ptrtoint ptr inttoptr (i64 7 to ptr) to i64
  %v2239 = and i64 %v2237, %v2238
  %v2240 = and i64 %v2239, 1
  %v2241 = icmp ne i64 %v2240, 0
  br i1 %v2241, label %yes.2242, label %no.2243
yes.2242:
  %v2245 = sub i64 %v2238, 1
  %v2246 = call { i64, i1 } @llvm.sadd.with.overflow.i64(i64 %v2237, i64 %v2245)
  %v2247 = extractvalue { i64, i1 } %v2246, 0
  %v2248 = extractvalue { i64, i1 } %v2246, 1
  br i1 %v2248, label %yes.2249, label %no.2250
yes.2249:
  %v2252 = call ptr @mlf_add_int(ptr %a1, ptr inttoptr (i64 7 to ptr))
  br label %join.2251
no.2250:
  %v2253 = inttoptr i64 %v2247 to ptr
  br label %join.2251
join.2251:
  %v2254 = phi ptr [ %v2252, %yes.2249 ], [ %v2253, %no.2250 ]
  br label %join.2244
no.2243:
  %v2255 = call ptr @mlf_add_int(ptr %a1, ptr inttoptr (i64 7 to ptr))
  br label %join.2244
join.2244:
  %v2256 = phi ptr [ %v2254, %join.2251 ], [ %v2255, %no.2243 ]
  %v2257 = getelementptr i8, ptr %a0, i64 24
  %v2258 = load i64, ptr %v2257, align 8, !tbaa !3
  %v2259 = getelementptr i8, ptr %a0, i64 32
  %v2260 = load ptr, ptr %v2259, align 8, !tbaa !3
  %v2261 = ptrtoint ptr %v2256 to i64
  %v2262 = ashr i64 %v2261, 1
  %v2263 = and i64 %v2261, 1
  %v2264 = icmp ne i64 %v2263, 0
  %v2265 = icmp ult i64 %v2262, %v2258
  %v2266 = and i1 %v2264, %v2265
  br i1 %v2266, label %array.valid.2267, label %array.invalid.2268
array.invalid.2268:
  call void @mlf_bounds_failure()
  unreachable
array.valid.2267:
  %v2269 = getelementptr i64, ptr %v2260, i64 %v2262
  %v2270 = load double, ptr %v2269, align 8, !tbaa !4
  %v2271 = ptrtoint ptr %a1 to i64
  %v2272 = ptrtoint ptr inttoptr (i64 9 to ptr) to i64
  %v2273 = and i64 %v2271, %v2272
  %v2274 = and i64 %v2273, 1
  %v2275 = icmp ne i64 %v2274, 0
  br i1 %v2275, label %yes.2276, label %no.2277
yes.2276:
  %v2279 = sub i64 %v2272, 1
  %v2280 = call { i64, i1 } @llvm.sadd.with.overflow.i64(i64 %v2271, i64 %v2279)
  %v2281 = extractvalue { i64, i1 } %v2280, 0
  %v2282 = extractvalue { i64, i1 } %v2280, 1
  br i1 %v2282, label %yes.2283, label %no.2284
yes.2283:
  %v2286 = call ptr @mlf_add_int(ptr %a1, ptr inttoptr (i64 9 to ptr))
  br label %join.2285
no.2284:
  %v2287 = inttoptr i64 %v2281 to ptr
  br label %join.2285
join.2285:
  %v2288 = phi ptr [ %v2286, %yes.2283 ], [ %v2287, %no.2284 ]
  br label %join.2278
no.2277:
  %v2289 = call ptr @mlf_add_int(ptr %a1, ptr inttoptr (i64 9 to ptr))
  br label %join.2278
join.2278:
  %v2290 = phi ptr [ %v2288, %join.2285 ], [ %v2289, %no.2277 ]
  %v2291 = ptrtoint ptr %v2290 to i64
  %v2292 = ashr i64 %v2291, 1
  %v2293 = and i64 %v2291, 1
  %v2294 = icmp ne i64 %v2293, 0
  %v2295 = icmp ult i64 %v2292, %v2258
  %v2296 = and i1 %v2294, %v2295
  br i1 %v2296, label %array.valid.2297, label %array.invalid.2298
array.invalid.2298:
  call void @mlf_bounds_failure()
  unreachable
array.valid.2297:
  %v2299 = getelementptr i64, ptr %v2260, i64 %v2292
  %v2300 = load double, ptr %v2299, align 8, !tbaa !4
  %v2301 = ptrtoint ptr %a1 to i64
  %v2302 = ptrtoint ptr inttoptr (i64 11 to ptr) to i64
  %v2303 = and i64 %v2301, %v2302
  %v2304 = and i64 %v2303, 1
  %v2305 = icmp ne i64 %v2304, 0
  br i1 %v2305, label %yes.2306, label %no.2307
yes.2306:
  %v2309 = sub i64 %v2302, 1
  %v2310 = call { i64, i1 } @llvm.sadd.with.overflow.i64(i64 %v2301, i64 %v2309)
  %v2311 = extractvalue { i64, i1 } %v2310, 0
  %v2312 = extractvalue { i64, i1 } %v2310, 1
  br i1 %v2312, label %yes.2313, label %no.2314
yes.2313:
  %v2316 = call ptr @mlf_add_int(ptr %a1, ptr inttoptr (i64 11 to ptr))
  br label %join.2315
no.2314:
  %v2317 = inttoptr i64 %v2311 to ptr
  br label %join.2315
join.2315:
  %v2318 = phi ptr [ %v2316, %yes.2313 ], [ %v2317, %no.2314 ]
  br label %join.2308
no.2307:
  %v2319 = call ptr @mlf_add_int(ptr %a1, ptr inttoptr (i64 11 to ptr))
  br label %join.2308
join.2308:
  %v2320 = phi ptr [ %v2318, %join.2315 ], [ %v2319, %no.2307 ]
  %v2321 = ptrtoint ptr %v2320 to i64
  %v2322 = ashr i64 %v2321, 1
  %v2323 = and i64 %v2321, 1
  %v2324 = icmp ne i64 %v2323, 0
  %v2325 = icmp ult i64 %v2322, %v2258
  %v2326 = and i1 %v2324, %v2325
  br i1 %v2326, label %array.valid.2327, label %array.invalid.2328
array.invalid.2328:
  call void @mlf_bounds_failure()
  unreachable
array.valid.2327:
  %v2329 = getelementptr i64, ptr %v2260, i64 %v2322
  %v2330 = load double, ptr %v2329, align 8, !tbaa !4
  %v2331 = ptrtoint ptr %a1 to i64
  %v2332 = ptrtoint ptr inttoptr (i64 13 to ptr) to i64
  %v2333 = and i64 %v2331, %v2332
  %v2334 = and i64 %v2333, 1
  %v2335 = icmp ne i64 %v2334, 0
  br i1 %v2335, label %yes.2336, label %no.2337
yes.2336:
  %v2339 = sub i64 %v2332, 1
  %v2340 = call { i64, i1 } @llvm.sadd.with.overflow.i64(i64 %v2331, i64 %v2339)
  %v2341 = extractvalue { i64, i1 } %v2340, 0
  %v2342 = extractvalue { i64, i1 } %v2340, 1
  br i1 %v2342, label %yes.2343, label %no.2344
yes.2343:
  %v2346 = call ptr @mlf_add_int(ptr %a1, ptr inttoptr (i64 13 to ptr))
  br label %join.2345
no.2344:
  %v2347 = inttoptr i64 %v2341 to ptr
  br label %join.2345
join.2345:
  %v2348 = phi ptr [ %v2346, %yes.2343 ], [ %v2347, %no.2344 ]
  br label %join.2338
no.2337:
  %v2349 = call ptr @mlf_add_int(ptr %a1, ptr inttoptr (i64 13 to ptr))
  br label %join.2338
join.2338:
  %v2350 = phi ptr [ %v2348, %join.2345 ], [ %v2349, %no.2337 ]
  %v2351 = ptrtoint ptr %v2350 to i64
  %v2352 = ashr i64 %v2351, 1
  %v2353 = and i64 %v2351, 1
  %v2354 = icmp ne i64 %v2353, 0
  %v2355 = icmp ult i64 %v2352, %v2258
  %v2356 = and i1 %v2354, %v2355
  br i1 %v2356, label %array.valid.2357, label %array.invalid.2358
array.invalid.2358:
  call void @mlf_bounds_failure()
  unreachable
array.valid.2357:
  %v2359 = getelementptr i64, ptr %v2260, i64 %v2352
  %v2360 = load double, ptr %v2359, align 8, !tbaa !4
  %v2361 = ptrtoint ptr %a1 to i64
  %v2362 = ptrtoint ptr inttoptr (i64 15 to ptr) to i64
  %v2363 = and i64 %v2361, %v2362
  %v2364 = and i64 %v2363, 1
  %v2365 = icmp ne i64 %v2364, 0
  br i1 %v2365, label %yes.2366, label %no.2367
yes.2366:
  %v2369 = sub i64 %v2362, 1
  %v2370 = call { i64, i1 } @llvm.sadd.with.overflow.i64(i64 %v2361, i64 %v2369)
  %v2371 = extractvalue { i64, i1 } %v2370, 0
  %v2372 = extractvalue { i64, i1 } %v2370, 1
  br i1 %v2372, label %yes.2373, label %no.2374
yes.2373:
  %v2376 = call ptr @mlf_add_int(ptr %a1, ptr inttoptr (i64 15 to ptr))
  br label %join.2375
no.2374:
  %v2377 = inttoptr i64 %v2371 to ptr
  br label %join.2375
join.2375:
  %v2378 = phi ptr [ %v2376, %yes.2373 ], [ %v2377, %no.2374 ]
  br label %join.2368
no.2367:
  %v2379 = call ptr @mlf_add_int(ptr %a1, ptr inttoptr (i64 15 to ptr))
  br label %join.2368
join.2368:
  %v2380 = phi ptr [ %v2378, %join.2375 ], [ %v2379, %no.2367 ]
  %v2381 = fmul double 0x3fe0000000000000, %v2360
  %v2382 = fmul double %v2270, %v2270
  %v2383 = fmul double %v2300, %v2300
  %v2384 = fadd double %v2382, %v2383
  %v2385 = fmul double %v2330, %v2330
  %v2386 = fadd double %v2384, %v2385
  %v2387 = fmul double %v2381, %v2386
  %v2388 = getelementptr i8, ptr %a2, i64 24
  %v2389 = load double, ptr %v2388, align 8, !tbaa !3
  %v2390 = fadd double %v2389, %v2387
  %v2539 = call ptr @mlf.numeric.16.pppd(ptr %a0, ptr %a1, ptr %v2380, double %v2390)
  %v2540 = ptrtoint ptr %a1 to i64
  %v2541 = ptrtoint ptr inttoptr (i64 15 to ptr) to i64
  %v2542 = and i64 %v2540, %v2541
  %v2543 = and i64 %v2542, 1
  %v2544 = icmp ne i64 %v2543, 0
  br i1 %v2544, label %yes.2545, label %no.2546
yes.2545:
  %v2548 = sub i64 %v2541, 1
  %v2549 = call { i64, i1 } @llvm.sadd.with.overflow.i64(i64 %v2540, i64 %v2548)
  %v2550 = extractvalue { i64, i1 } %v2549, 0
  %v2551 = extractvalue { i64, i1 } %v2549, 1
  br i1 %v2551, label %yes.2552, label %no.2553
yes.2552:
  %v2555 = call ptr @mlf_add_int(ptr %a1, ptr inttoptr (i64 15 to ptr))
  br label %join.2554
no.2553:
  %v2556 = inttoptr i64 %v2550 to ptr
  br label %join.2554
join.2554:
  %v2557 = phi ptr [ %v2555, %yes.2552 ], [ %v2556, %no.2553 ]
  br label %join.2547
no.2546:
  %v2558 = call ptr @mlf_add_int(ptr %a1, ptr inttoptr (i64 15 to ptr))
  br label %join.2547
join.2547:
  %v2559 = phi ptr [ %v2557, %join.2554 ], [ %v2558, %no.2546 ]
  %v2560 = musttail call ptr @mlf.numeric.33(ptr %a0, ptr %v2559, ptr %v2539)
  ret ptr %v2560
}

define private ptr @mlf.code.2574(ptr %env, ptr %arg) {
entry:
  %v2575 = getelementptr i8, ptr %env, i64 24
  %v2576 = load ptr, ptr %v2575, align 8, !tbaa !3
  %v2577 = call ptr @mlf_force(ptr %v2576)
  %v2578 = call ptr @mlf_prim2(i64 8, ptr %v2577, ptr inttoptr (i64 7 to ptr))
  ret ptr %v2578
}

define private ptr @mlf.code.2569(ptr %env, ptr %arg) {
entry:
  %v2570 = getelementptr i8, ptr %env, i64 24
  %v2571 = load ptr, ptr %v2570, align 8, !tbaa !3
  %v2572 = getelementptr i8, ptr %env, i64 32
  %v2573 = load ptr, ptr %v2572, align 8, !tbaa !3
  %v2579 = call ptr @mlf_env_new(i64 1)
  %v2580 = getelementptr i8, ptr %v2579, i64 24
  store ptr %v2573, ptr %v2580, align 8, !tbaa !3
  %v2581 = call ptr @mlf_thunk(ptr @mlf.code.2574, ptr %v2579)
  %v2582 = call ptr @mlf_prim2(i64 32, ptr %v2571, ptr %v2581)
  ret ptr %v2582
}

define private ptr @mlf.code.2599(ptr %env, ptr %arg) {
entry:
  %v2600 = getelementptr i8, ptr %env, i64 24
  %v2601 = load ptr, ptr %v2600, align 8, !tbaa !3
  %v2602 = call ptr @mlf_force(ptr %v2601)
  %v2603 = call ptr @mlf_prim2(i64 8, ptr %v2602, ptr inttoptr (i64 9 to ptr))
  ret ptr %v2603
}

define private ptr @mlf.code.2594(ptr %env, ptr %arg) {
entry:
  %v2595 = getelementptr i8, ptr %env, i64 24
  %v2596 = load ptr, ptr %v2595, align 8, !tbaa !3
  %v2597 = getelementptr i8, ptr %env, i64 32
  %v2598 = load ptr, ptr %v2597, align 8, !tbaa !3
  %v2604 = call ptr @mlf_env_new(i64 1)
  %v2605 = getelementptr i8, ptr %v2604, i64 24
  store ptr %v2598, ptr %v2605, align 8, !tbaa !3
  %v2606 = call ptr @mlf_thunk(ptr @mlf.code.2599, ptr %v2604)
  %v2607 = call ptr @mlf_prim2(i64 32, ptr %v2596, ptr %v2606)
  ret ptr %v2607
}

define private ptr @mlf.code.2626(ptr %env, ptr %arg) {
entry:
  %v2627 = getelementptr i8, ptr %env, i64 24
  %v2628 = load ptr, ptr %v2627, align 8, !tbaa !3
  %v2629 = call ptr @mlf_force(ptr %v2628)
  %v2630 = call ptr @mlf_prim2(i64 8, ptr %v2629, ptr inttoptr (i64 11 to ptr))
  ret ptr %v2630
}

define private ptr @mlf.code.2621(ptr %env, ptr %arg) {
entry:
  %v2622 = getelementptr i8, ptr %env, i64 24
  %v2623 = load ptr, ptr %v2622, align 8, !tbaa !3
  %v2624 = getelementptr i8, ptr %env, i64 32
  %v2625 = load ptr, ptr %v2624, align 8, !tbaa !3
  %v2631 = call ptr @mlf_env_new(i64 1)
  %v2632 = getelementptr i8, ptr %v2631, i64 24
  store ptr %v2625, ptr %v2632, align 8, !tbaa !3
  %v2633 = call ptr @mlf_thunk(ptr @mlf.code.2626, ptr %v2631)
  %v2634 = call ptr @mlf_prim2(i64 32, ptr %v2623, ptr %v2633)
  ret ptr %v2634
}

define private ptr @mlf.code.2655(ptr %env, ptr %arg) {
entry:
  %v2656 = getelementptr i8, ptr %env, i64 24
  %v2657 = load ptr, ptr %v2656, align 8, !tbaa !3
  %v2658 = call ptr @mlf_force(ptr %v2657)
  %v2659 = call ptr @mlf_prim2(i64 8, ptr %v2658, ptr inttoptr (i64 13 to ptr))
  ret ptr %v2659
}

define private ptr @mlf.code.2650(ptr %env, ptr %arg) {
entry:
  %v2651 = getelementptr i8, ptr %env, i64 24
  %v2652 = load ptr, ptr %v2651, align 8, !tbaa !3
  %v2653 = getelementptr i8, ptr %env, i64 32
  %v2654 = load ptr, ptr %v2653, align 8, !tbaa !3
  %v2660 = call ptr @mlf_env_new(i64 1)
  %v2661 = getelementptr i8, ptr %v2660, i64 24
  store ptr %v2654, ptr %v2661, align 8, !tbaa !3
  %v2662 = call ptr @mlf_thunk(ptr @mlf.code.2655, ptr %v2660)
  %v2663 = call ptr @mlf_prim2(i64 32, ptr %v2652, ptr %v2662)
  ret ptr %v2663
}

define private ptr @mlf.numeric.16(ptr %a0, ptr %a1, ptr %a2, ptr %a3) alwaysinline {
entry:
  %v2720 = ptrtoint ptr %a2 to i64
  %v2721 = ptrtoint ptr inttoptr (i64 71 to ptr) to i64
  %v2722 = and i64 %v2720, %v2721
  %v2723 = and i64 %v2722, 1
  %v2724 = icmp ne i64 %v2723, 0
  br i1 %v2724, label %yes.2725, label %no.2726
yes.2725:
  %v2728 = icmp eq i64 %v2720, %v2721
  %v2729 = select i1 %v2728, ptr inttoptr (i64 6 to ptr), ptr inttoptr (i64 2 to ptr)
  br label %join.2727
no.2726:
  %v2730 = call ptr @mlf_eq_int(ptr %a2, ptr inttoptr (i64 71 to ptr))
  br label %join.2727
join.2727:
  %v2731 = phi ptr [ %v2729, %yes.2725 ], [ %v2730, %no.2726 ]
  %v2732 = icmp eq ptr %v2731, inttoptr (i64 6 to ptr)
  br i1 %v2732, label %tail.yes.2733, label %tail.no.2734
tail.yes.2733:
  ret ptr %a3
tail.no.2734:
  %v2735 = getelementptr i8, ptr %a0, i64 24
  %v2736 = load i64, ptr %v2735, align 8, !tbaa !3
  %v2737 = getelementptr i8, ptr %a0, i64 32
  %v2738 = load ptr, ptr %v2737, align 8, !tbaa !3
  %v2739 = ptrtoint ptr %a1 to i64
  %v2740 = ashr i64 %v2739, 1
  %v2741 = and i64 %v2739, 1
  %v2742 = icmp ne i64 %v2741, 0
  %v2743 = icmp ult i64 %v2740, %v2736
  %v2744 = and i1 %v2742, %v2743
  br i1 %v2744, label %array.valid.2745, label %array.invalid.2746
array.invalid.2746:
  call void @mlf_bounds_failure()
  unreachable
array.valid.2745:
  %v2747 = getelementptr i64, ptr %v2738, i64 %v2740
  %v2748 = load double, ptr %v2747, align 8, !tbaa !4
  %v2749 = ptrtoint ptr %a1 to i64
  %v2750 = ptrtoint ptr inttoptr (i64 3 to ptr) to i64
  %v2751 = sub i64 %v2750, 1
  %v2752 = add nsw i64 %v2749, %v2751
  %v2753 = inttoptr i64 %v2752 to ptr
  %v2754 = ptrtoint ptr %v2753 to i64
  %v2755 = ashr i64 %v2754, 1
  %v2756 = and i64 %v2754, 1
  %v2757 = icmp ne i64 %v2756, 0
  %v2758 = icmp ult i64 %v2755, %v2736
  %v2759 = and i1 %v2757, %v2758
  br i1 %v2759, label %array.valid.2760, label %array.invalid.2761
array.invalid.2761:
  call void @mlf_bounds_failure()
  unreachable
array.valid.2760:
  %v2762 = getelementptr i64, ptr %v2738, i64 %v2755
  %v2763 = load double, ptr %v2762, align 8, !tbaa !4
  %v2764 = ptrtoint ptr %a1 to i64
  %v2765 = ptrtoint ptr inttoptr (i64 5 to ptr) to i64
  %v2766 = sub i64 %v2765, 1
  %v2767 = add nsw i64 %v2764, %v2766
  %v2768 = inttoptr i64 %v2767 to ptr
  %v2769 = ptrtoint ptr %v2768 to i64
  %v2770 = ashr i64 %v2769, 1
  %v2771 = and i64 %v2769, 1
  %v2772 = icmp ne i64 %v2771, 0
  %v2773 = icmp ult i64 %v2770, %v2736
  %v2774 = and i1 %v2772, %v2773
  br i1 %v2774, label %array.valid.2775, label %array.invalid.2776
array.invalid.2776:
  call void @mlf_bounds_failure()
  unreachable
array.valid.2775:
  %v2777 = getelementptr i64, ptr %v2738, i64 %v2770
  %v2778 = load double, ptr %v2777, align 8, !tbaa !4
  %v2779 = ptrtoint ptr %a1 to i64
  %v2780 = ptrtoint ptr inttoptr (i64 13 to ptr) to i64
  %v2781 = sub i64 %v2780, 1
  %v2782 = add nsw i64 %v2779, %v2781
  %v2783 = inttoptr i64 %v2782 to ptr
  %v2784 = ptrtoint ptr %v2783 to i64
  %v2785 = ashr i64 %v2784, 1
  %v2786 = and i64 %v2784, 1
  %v2787 = icmp ne i64 %v2786, 0
  %v2788 = icmp ult i64 %v2785, %v2736
  %v2789 = and i1 %v2787, %v2788
  br i1 %v2789, label %array.valid.2790, label %array.invalid.2791
array.invalid.2791:
  call void @mlf_bounds_failure()
  unreachable
array.valid.2790:
  %v2792 = getelementptr i64, ptr %v2738, i64 %v2785
  %v2793 = load double, ptr %v2792, align 8, !tbaa !4
  %v2794 = ptrtoint ptr %a2 to i64
  %v2795 = ashr i64 %v2794, 1
  %v2796 = and i64 %v2794, 1
  %v2797 = icmp ne i64 %v2796, 0
  %v2798 = icmp ult i64 %v2795, %v2736
  %v2799 = and i1 %v2797, %v2798
  br i1 %v2799, label %array.valid.2800, label %array.invalid.2801
array.invalid.2801:
  call void @mlf_bounds_failure()
  unreachable
array.valid.2800:
  %v2802 = getelementptr i64, ptr %v2738, i64 %v2795
  %v2803 = load double, ptr %v2802, align 8, !tbaa !4
  %v2804 = ptrtoint ptr %a2 to i64
  %v2805 = ptrtoint ptr inttoptr (i64 3 to ptr) to i64
  %v2806 = sub i64 %v2805, 1
  %v2807 = add nsw i64 %v2804, %v2806
  %v2808 = inttoptr i64 %v2807 to ptr
  %v2809 = ptrtoint ptr %v2808 to i64
  %v2810 = ashr i64 %v2809, 1
  %v2811 = and i64 %v2809, 1
  %v2812 = icmp ne i64 %v2811, 0
  %v2813 = icmp ult i64 %v2810, %v2736
  %v2814 = and i1 %v2812, %v2813
  br i1 %v2814, label %array.valid.2815, label %array.invalid.2816
array.invalid.2816:
  call void @mlf_bounds_failure()
  unreachable
array.valid.2815:
  %v2817 = getelementptr i64, ptr %v2738, i64 %v2810
  %v2818 = load double, ptr %v2817, align 8, !tbaa !4
  %v2819 = ptrtoint ptr %a2 to i64
  %v2820 = ptrtoint ptr inttoptr (i64 5 to ptr) to i64
  %v2821 = sub i64 %v2820, 1
  %v2822 = add nsw i64 %v2819, %v2821
  %v2823 = inttoptr i64 %v2822 to ptr
  %v2824 = ptrtoint ptr %v2823 to i64
  %v2825 = ashr i64 %v2824, 1
  %v2826 = and i64 %v2824, 1
  %v2827 = icmp ne i64 %v2826, 0
  %v2828 = icmp ult i64 %v2825, %v2736
  %v2829 = and i1 %v2827, %v2828
  br i1 %v2829, label %array.valid.2830, label %array.invalid.2831
array.invalid.2831:
  call void @mlf_bounds_failure()
  unreachable
array.valid.2830:
  %v2832 = getelementptr i64, ptr %v2738, i64 %v2825
  %v2833 = load double, ptr %v2832, align 8, !tbaa !4
  %v2834 = ptrtoint ptr %a2 to i64
  %v2835 = ptrtoint ptr inttoptr (i64 13 to ptr) to i64
  %v2836 = sub i64 %v2835, 1
  %v2837 = add nsw i64 %v2834, %v2836
  %v2838 = inttoptr i64 %v2837 to ptr
  %v2839 = ptrtoint ptr %v2838 to i64
  %v2840 = ashr i64 %v2839, 1
  %v2841 = and i64 %v2839, 1
  %v2842 = icmp ne i64 %v2841, 0
  %v2843 = icmp ult i64 %v2840, %v2736
  %v2844 = and i1 %v2842, %v2843
  br i1 %v2844, label %array.valid.2845, label %array.invalid.2846
array.invalid.2846:
  call void @mlf_bounds_failure()
  unreachable
array.valid.2845:
  %v2847 = getelementptr i64, ptr %v2738, i64 %v2840
  %v2848 = load double, ptr %v2847, align 8, !tbaa !4
  %v2849 = fsub double %v2748, %v2803
  %v2850 = fsub double %v2763, %v2818
  %v2851 = fsub double %v2778, %v2833
  %v2852 = fmul double %v2849, %v2849
  %v2853 = fmul double %v2850, %v2850
  %v2854 = fadd double %v2852, %v2853
  %v2855 = fmul double %v2851, %v2851
  %v2856 = fadd double %v2854, %v2855
  %v2857 = call double @llvm.sqrt.f64(double %v2856)
  %v2858 = ptrtoint ptr %a2 to i64
  %v2859 = ptrtoint ptr inttoptr (i64 15 to ptr) to i64
  %v2860 = sub i64 %v2859, 1
  %v2861 = add nsw i64 %v2858, %v2860
  %v2862 = inttoptr i64 %v2861 to ptr
  %v2863 = fmul double %v2793, %v2848
  %v2864 = fdiv double %v2863, %v2857
  %v2865 = getelementptr i8, ptr %a3, i64 24
  %v2866 = load double, ptr %v2865, align 8, !tbaa !3
  %v2867 = fsub double %v2866, %v2864
  %v2868 = call ptr @mlf.numeric.16.pppd(ptr %a0, ptr %a1, ptr %v2862, double %v2867)
  ret ptr %v2868
}

define private ptr @mlf.code.2882(ptr %env, ptr %arg) {
entry:
  %v2883 = getelementptr i8, ptr %env, i64 24
  %v2884 = load ptr, ptr %v2883, align 8, !tbaa !3
  %v2885 = call ptr @mlf_force(ptr %v2884)
  %v2886 = call ptr @mlf_prim2(i64 8, ptr %v2885, ptr inttoptr (i64 1 to ptr))
  ret ptr %v2886
}

define private ptr @mlf.code.2877(ptr %env, ptr %arg) {
entry:
  %v2878 = getelementptr i8, ptr %env, i64 24
  %v2879 = load ptr, ptr %v2878, align 8, !tbaa !3
  %v2880 = getelementptr i8, ptr %env, i64 32
  %v2881 = load ptr, ptr %v2880, align 8, !tbaa !3
  %v2887 = call ptr @mlf_env_new(i64 1)
  %v2888 = getelementptr i8, ptr %v2887, i64 24
  store ptr %v2881, ptr %v2888, align 8, !tbaa !3
  %v2889 = call ptr @mlf_thunk(ptr @mlf.code.2882, ptr %v2887)
  %v2890 = call ptr @mlf_prim2(i64 32, ptr %v2879, ptr %v2889)
  ret ptr %v2890
}

define private ptr @mlf.code.2909(ptr %env, ptr %arg) {
entry:
  %v2910 = getelementptr i8, ptr %env, i64 24
  %v2911 = load ptr, ptr %v2910, align 8, !tbaa !3
  %v2912 = call ptr @mlf_force(ptr %v2911)
  %v2913 = call ptr @mlf_prim2(i64 8, ptr %v2912, ptr inttoptr (i64 3 to ptr))
  ret ptr %v2913
}

define private ptr @mlf.code.2904(ptr %env, ptr %arg) {
entry:
  %v2905 = getelementptr i8, ptr %env, i64 24
  %v2906 = load ptr, ptr %v2905, align 8, !tbaa !3
  %v2907 = getelementptr i8, ptr %env, i64 32
  %v2908 = load ptr, ptr %v2907, align 8, !tbaa !3
  %v2914 = call ptr @mlf_env_new(i64 1)
  %v2915 = getelementptr i8, ptr %v2914, i64 24
  store ptr %v2908, ptr %v2915, align 8, !tbaa !3
  %v2916 = call ptr @mlf_thunk(ptr @mlf.code.2909, ptr %v2914)
  %v2917 = call ptr @mlf_prim2(i64 32, ptr %v2906, ptr %v2916)
  ret ptr %v2917
}

define private ptr @mlf.code.2938(ptr %env, ptr %arg) {
entry:
  %v2939 = getelementptr i8, ptr %env, i64 24
  %v2940 = load ptr, ptr %v2939, align 8, !tbaa !3
  %v2941 = call ptr @mlf_force(ptr %v2940)
  %v2942 = call ptr @mlf_prim2(i64 8, ptr %v2941, ptr inttoptr (i64 5 to ptr))
  ret ptr %v2942
}

define private ptr @mlf.code.2933(ptr %env, ptr %arg) {
entry:
  %v2934 = getelementptr i8, ptr %env, i64 24
  %v2935 = load ptr, ptr %v2934, align 8, !tbaa !3
  %v2936 = getelementptr i8, ptr %env, i64 32
  %v2937 = load ptr, ptr %v2936, align 8, !tbaa !3
  %v2943 = call ptr @mlf_env_new(i64 1)
  %v2944 = getelementptr i8, ptr %v2943, i64 24
  store ptr %v2937, ptr %v2944, align 8, !tbaa !3
  %v2945 = call ptr @mlf_thunk(ptr @mlf.code.2938, ptr %v2943)
  %v2946 = call ptr @mlf_prim2(i64 32, ptr %v2935, ptr %v2945)
  ret ptr %v2946
}

define private ptr @mlf.code.2969(ptr %env, ptr %arg) {
entry:
  %v2970 = getelementptr i8, ptr %env, i64 24
  %v2971 = load ptr, ptr %v2970, align 8, !tbaa !3
  %v2972 = call ptr @mlf_force(ptr %v2971)
  %v2973 = call ptr @mlf_prim2(i64 8, ptr %v2972, ptr inttoptr (i64 13 to ptr))
  ret ptr %v2973
}

define private ptr @mlf.code.2964(ptr %env, ptr %arg) {
entry:
  %v2965 = getelementptr i8, ptr %env, i64 24
  %v2966 = load ptr, ptr %v2965, align 8, !tbaa !3
  %v2967 = getelementptr i8, ptr %env, i64 32
  %v2968 = load ptr, ptr %v2967, align 8, !tbaa !3
  %v2974 = call ptr @mlf_env_new(i64 1)
  %v2975 = getelementptr i8, ptr %v2974, i64 24
  store ptr %v2968, ptr %v2975, align 8, !tbaa !3
  %v2976 = call ptr @mlf_thunk(ptr @mlf.code.2969, ptr %v2974)
  %v2977 = call ptr @mlf_prim2(i64 32, ptr %v2966, ptr %v2976)
  ret ptr %v2977
}

define private ptr @mlf.code.3002(ptr %env, ptr %arg) {
entry:
  %v3003 = getelementptr i8, ptr %env, i64 24
  %v3004 = load ptr, ptr %v3003, align 8, !tbaa !3
  %v3005 = call ptr @mlf_force(ptr %v3004)
  %v3006 = call ptr @mlf_prim2(i64 8, ptr %v3005, ptr inttoptr (i64 1 to ptr))
  ret ptr %v3006
}

define private ptr @mlf.code.2997(ptr %env, ptr %arg) {
entry:
  %v2998 = getelementptr i8, ptr %env, i64 24
  %v2999 = load ptr, ptr %v2998, align 8, !tbaa !3
  %v3000 = getelementptr i8, ptr %env, i64 32
  %v3001 = load ptr, ptr %v3000, align 8, !tbaa !3
  %v3007 = call ptr @mlf_env_new(i64 1)
  %v3008 = getelementptr i8, ptr %v3007, i64 24
  store ptr %v3001, ptr %v3008, align 8, !tbaa !3
  %v3009 = call ptr @mlf_thunk(ptr @mlf.code.3002, ptr %v3007)
  %v3010 = call ptr @mlf_prim2(i64 32, ptr %v2999, ptr %v3009)
  ret ptr %v3010
}

define private ptr @mlf.code.3037(ptr %env, ptr %arg) {
entry:
  %v3038 = getelementptr i8, ptr %env, i64 24
  %v3039 = load ptr, ptr %v3038, align 8, !tbaa !3
  %v3040 = call ptr @mlf_force(ptr %v3039)
  %v3041 = call ptr @mlf_prim2(i64 8, ptr %v3040, ptr inttoptr (i64 3 to ptr))
  ret ptr %v3041
}

define private ptr @mlf.code.3032(ptr %env, ptr %arg) {
entry:
  %v3033 = getelementptr i8, ptr %env, i64 24
  %v3034 = load ptr, ptr %v3033, align 8, !tbaa !3
  %v3035 = getelementptr i8, ptr %env, i64 32
  %v3036 = load ptr, ptr %v3035, align 8, !tbaa !3
  %v3042 = call ptr @mlf_env_new(i64 1)
  %v3043 = getelementptr i8, ptr %v3042, i64 24
  store ptr %v3036, ptr %v3043, align 8, !tbaa !3
  %v3044 = call ptr @mlf_thunk(ptr @mlf.code.3037, ptr %v3042)
  %v3045 = call ptr @mlf_prim2(i64 32, ptr %v3034, ptr %v3044)
  ret ptr %v3045
}

define private ptr @mlf.code.3074(ptr %env, ptr %arg) {
entry:
  %v3075 = getelementptr i8, ptr %env, i64 24
  %v3076 = load ptr, ptr %v3075, align 8, !tbaa !3
  %v3077 = call ptr @mlf_force(ptr %v3076)
  %v3078 = call ptr @mlf_prim2(i64 8, ptr %v3077, ptr inttoptr (i64 5 to ptr))
  ret ptr %v3078
}

define private ptr @mlf.code.3069(ptr %env, ptr %arg) {
entry:
  %v3070 = getelementptr i8, ptr %env, i64 24
  %v3071 = load ptr, ptr %v3070, align 8, !tbaa !3
  %v3072 = getelementptr i8, ptr %env, i64 32
  %v3073 = load ptr, ptr %v3072, align 8, !tbaa !3
  %v3079 = call ptr @mlf_env_new(i64 1)
  %v3080 = getelementptr i8, ptr %v3079, i64 24
  store ptr %v3073, ptr %v3080, align 8, !tbaa !3
  %v3081 = call ptr @mlf_thunk(ptr @mlf.code.3074, ptr %v3079)
  %v3082 = call ptr @mlf_prim2(i64 32, ptr %v3071, ptr %v3081)
  ret ptr %v3082
}

define private ptr @mlf.code.3113(ptr %env, ptr %arg) {
entry:
  %v3114 = getelementptr i8, ptr %env, i64 24
  %v3115 = load ptr, ptr %v3114, align 8, !tbaa !3
  %v3116 = call ptr @mlf_force(ptr %v3115)
  %v3117 = call ptr @mlf_prim2(i64 8, ptr %v3116, ptr inttoptr (i64 13 to ptr))
  ret ptr %v3117
}

define private ptr @mlf.code.3108(ptr %env, ptr %arg) {
entry:
  %v3109 = getelementptr i8, ptr %env, i64 24
  %v3110 = load ptr, ptr %v3109, align 8, !tbaa !3
  %v3111 = getelementptr i8, ptr %env, i64 32
  %v3112 = load ptr, ptr %v3111, align 8, !tbaa !3
  %v3118 = call ptr @mlf_env_new(i64 1)
  %v3119 = getelementptr i8, ptr %v3118, i64 24
  store ptr %v3112, ptr %v3119, align 8, !tbaa !3
  %v3120 = call ptr @mlf_thunk(ptr @mlf.code.3113, ptr %v3118)
  %v3121 = call ptr @mlf_prim2(i64 32, ptr %v3110, ptr %v3120)
  ret ptr %v3121
}

define private ptr @mlf.code.3149(ptr %env, ptr %arg) {
entry:
  %v3150 = getelementptr i8, ptr %env, i64 24
  %v3151 = load ptr, ptr %v3150, align 8, !tbaa !3
  %v3152 = getelementptr i8, ptr %env, i64 32
  %v3153 = load ptr, ptr %v3152, align 8, !tbaa !3
  %v3154 = getelementptr i8, ptr %env, i64 40
  %v3155 = load ptr, ptr %v3154, align 8, !tbaa !3
  %v3156 = getelementptr i8, ptr %env, i64 48
  %v3157 = load ptr, ptr %v3156, align 8, !tbaa !3
  %v3158 = getelementptr i8, ptr %env, i64 56
  %v3159 = load ptr, ptr %v3158, align 8, !tbaa !3
  %v3160 = getelementptr i8, ptr %env, i64 64
  %v3161 = load ptr, ptr %v3160, align 8, !tbaa !3
  %v3162 = call ptr @mlf_force(ptr %v3151)
  %v3163 = call ptr @mlf_force(ptr %v3157)
  %v3164 = call ptr @mlf_prim2(i64 19, ptr %v3162, ptr %v3163)
  %v3165 = call ptr @mlf_force(ptr %v3153)
  %v3166 = call ptr @mlf_force(ptr %v3159)
  %v3167 = call ptr @mlf_prim2(i64 19, ptr %v3165, ptr %v3166)
  %v3168 = call ptr @mlf_force(ptr %v3155)
  %v3169 = call ptr @mlf_force(ptr %v3161)
  %v3170 = call ptr @mlf_prim2(i64 19, ptr %v3168, ptr %v3169)
  %v3171 = call ptr @mlf_prim2(i64 20, ptr %v3164, ptr %v3164)
  %v3172 = call ptr @mlf_prim2(i64 20, ptr %v3167, ptr %v3167)
  %v3173 = call ptr @mlf_prim2(i64 18, ptr %v3171, ptr %v3172)
  %v3174 = call ptr @mlf_prim2(i64 20, ptr %v3170, ptr %v3170)
  %v3175 = call ptr @mlf_prim2(i64 18, ptr %v3173, ptr %v3174)
  %v3176 = call ptr @mlf_prim1(i64 22, ptr %v3175)
  ret ptr %v3176
}

define private ptr @mlf.code.3187(ptr %env, ptr %arg) {
entry:
  %v3188 = getelementptr i8, ptr %env, i64 24
  %v3189 = load ptr, ptr %v3188, align 8, !tbaa !3
  %v3190 = getelementptr i8, ptr %env, i64 32
  %v3191 = load ptr, ptr %v3190, align 8, !tbaa !3
  %v3192 = getelementptr i8, ptr %env, i64 40
  %v3193 = load ptr, ptr %v3192, align 8, !tbaa !3
  %v3194 = getelementptr i8, ptr %env, i64 48
  %v3195 = load ptr, ptr %v3194, align 8, !tbaa !3
  %v3196 = call ptr @mlf_force(ptr %v3189)
  %v3197 = call ptr @mlf_force(ptr %v3191)
  %v3198 = call ptr @mlf_force(ptr %v3193)
  %v3199 = call ptr @mlf_prim2(i64 20, ptr %v3197, ptr %v3198)
  %v3200 = call ptr @mlf_force(ptr %v3195)
  %v3201 = call ptr @mlf_prim2(i64 21, ptr %v3199, ptr %v3200)
  %v3202 = call ptr @mlf_prim2(i64 19, ptr %v3196, ptr %v3201)
  ret ptr %v3202
}

define private ptr @mlf.code.3126(ptr %env, ptr %arg) {
entry:
  %v3127 = getelementptr i8, ptr %env, i64 24
  %v3128 = load ptr, ptr %v3127, align 8, !tbaa !3
  %v3129 = getelementptr i8, ptr %env, i64 32
  %v3130 = load ptr, ptr %v3129, align 8, !tbaa !3
  %v3131 = getelementptr i8, ptr %env, i64 40
  %v3132 = load ptr, ptr %v3131, align 8, !tbaa !3
  %v3133 = getelementptr i8, ptr %env, i64 48
  %v3134 = load ptr, ptr %v3133, align 8, !tbaa !3
  %v3135 = getelementptr i8, ptr %env, i64 56
  %v3136 = load ptr, ptr %v3135, align 8, !tbaa !3
  %v3137 = getelementptr i8, ptr %env, i64 64
  %v3138 = load ptr, ptr %v3137, align 8, !tbaa !3
  %v3139 = getelementptr i8, ptr %env, i64 72
  %v3140 = load ptr, ptr %v3139, align 8, !tbaa !3
  %v3141 = getelementptr i8, ptr %env, i64 80
  %v3142 = load ptr, ptr %v3141, align 8, !tbaa !3
  %v3143 = getelementptr i8, ptr %env, i64 88
  %v3144 = load ptr, ptr %v3143, align 8, !tbaa !3
  %v3145 = getelementptr i8, ptr %env, i64 96
  %v3146 = load ptr, ptr %v3145, align 8, !tbaa !3
  %v3147 = getelementptr i8, ptr %env, i64 104
  %v3148 = load ptr, ptr %v3147, align 8, !tbaa !3
  %v3177 = call ptr @mlf_env_new(i64 6)
  %v3178 = getelementptr i8, ptr %v3177, i64 24
  store ptr %v3136, ptr %v3178, align 8, !tbaa !3
  %v3179 = getelementptr i8, ptr %v3177, i64 32
  store ptr %v3138, ptr %v3179, align 8, !tbaa !3
  %v3180 = getelementptr i8, ptr %v3177, i64 40
  store ptr %v3140, ptr %v3180, align 8, !tbaa !3
  %v3181 = getelementptr i8, ptr %v3177, i64 48
  store ptr %v3144, ptr %v3181, align 8, !tbaa !3
  %v3182 = getelementptr i8, ptr %v3177, i64 56
  store ptr %v3146, ptr %v3182, align 8, !tbaa !3
  %v3183 = getelementptr i8, ptr %v3177, i64 64
  store ptr %v3148, ptr %v3183, align 8, !tbaa !3
  %v3184 = call ptr @mlf_thunk(ptr @mlf.code.3149, ptr %v3177)
  %v3185 = call ptr @mlf_force(ptr %v3132)
  %v3186 = call ptr @mlf_prim2(i64 8, ptr %v3185, ptr inttoptr (i64 15 to ptr))
  %v3203 = call ptr @mlf_env_new(i64 4)
  %v3204 = getelementptr i8, ptr %v3203, i64 24
  store ptr %v3134, ptr %v3204, align 8, !tbaa !3
  %v3205 = getelementptr i8, ptr %v3203, i64 32
  store ptr %v3142, ptr %v3205, align 8, !tbaa !3
  %v3206 = getelementptr i8, ptr %v3203, i64 40
  store ptr %arg, ptr %v3206, align 8, !tbaa !3
  %v3207 = getelementptr i8, ptr %v3203, i64 48
  store ptr %v3184, ptr %v3207, align 8, !tbaa !3
  %v3208 = call ptr @mlf_thunk(ptr @mlf.code.3187, ptr %v3203)
  %v3209 = call ptr @mlf_env_new(i64 4)
  %v3210 = getelementptr i8, ptr %v3209, i64 24
  store ptr %v3128, ptr %v3210, align 8, !tbaa !3
  %v3211 = getelementptr i8, ptr %v3209, i64 32
  store ptr %v3130, ptr %v3211, align 8, !tbaa !3
  %v3212 = getelementptr i8, ptr %v3209, i64 40
  store ptr %v3186, ptr %v3212, align 8, !tbaa !3
  %v3213 = getelementptr i8, ptr %v3209, i64 48
  store ptr %v3208, ptr %v3213, align 8, !tbaa !3
  %v3214 = call ptr @mlf_native_io(ptr @mlf.numeric.entry.2696, ptr %v3209)
  ret ptr %v3214
}

define private ptr @mlf.code.3087(ptr %env, ptr %arg) {
entry:
  %v3088 = getelementptr i8, ptr %env, i64 24
  %v3089 = load ptr, ptr %v3088, align 8, !tbaa !3
  %v3090 = getelementptr i8, ptr %env, i64 32
  %v3091 = load ptr, ptr %v3090, align 8, !tbaa !3
  %v3092 = getelementptr i8, ptr %env, i64 40
  %v3093 = load ptr, ptr %v3092, align 8, !tbaa !3
  %v3094 = getelementptr i8, ptr %env, i64 48
  %v3095 = load ptr, ptr %v3094, align 8, !tbaa !3
  %v3096 = getelementptr i8, ptr %env, i64 56
  %v3097 = load ptr, ptr %v3096, align 8, !tbaa !3
  %v3098 = getelementptr i8, ptr %env, i64 64
  %v3099 = load ptr, ptr %v3098, align 8, !tbaa !3
  %v3100 = getelementptr i8, ptr %env, i64 72
  %v3101 = load ptr, ptr %v3100, align 8, !tbaa !3
  %v3102 = getelementptr i8, ptr %env, i64 80
  %v3103 = load ptr, ptr %v3102, align 8, !tbaa !3
  %v3104 = getelementptr i8, ptr %env, i64 88
  %v3105 = load ptr, ptr %v3104, align 8, !tbaa !3
  %v3106 = getelementptr i8, ptr %env, i64 96
  %v3107 = load ptr, ptr %v3106, align 8, !tbaa !3
  %v3122 = call ptr @mlf_env_new(i64 2)
  %v3123 = getelementptr i8, ptr %v3122, i64 24
  store ptr %v3089, ptr %v3123, align 8, !tbaa !3
  %v3124 = getelementptr i8, ptr %v3122, i64 32
  store ptr %v3093, ptr %v3124, align 8, !tbaa !3
  %v3125 = call ptr @mlf_thunk(ptr @mlf.code.3108, ptr %v3122)
  %v3215 = call ptr @mlf_env_new(i64 11)
  %v3216 = getelementptr i8, ptr %v3215, i64 24
  store ptr %v3089, ptr %v3216, align 8, !tbaa !3
  %v3217 = getelementptr i8, ptr %v3215, i64 32
  store ptr %v3091, ptr %v3217, align 8, !tbaa !3
  %v3218 = getelementptr i8, ptr %v3215, i64 40
  store ptr %v3093, ptr %v3218, align 8, !tbaa !3
  %v3219 = getelementptr i8, ptr %v3215, i64 48
  store ptr %v3095, ptr %v3219, align 8, !tbaa !3
  %v3220 = getelementptr i8, ptr %v3215, i64 56
  store ptr %v3097, ptr %v3220, align 8, !tbaa !3
  %v3221 = getelementptr i8, ptr %v3215, i64 64
  store ptr %v3099, ptr %v3221, align 8, !tbaa !3
  %v3222 = getelementptr i8, ptr %v3215, i64 72
  store ptr %v3101, ptr %v3222, align 8, !tbaa !3
  %v3223 = getelementptr i8, ptr %v3215, i64 80
  store ptr %v3103, ptr %v3223, align 8, !tbaa !3
  %v3224 = getelementptr i8, ptr %v3215, i64 88
  store ptr %v3105, ptr %v3224, align 8, !tbaa !3
  %v3225 = getelementptr i8, ptr %v3215, i64 96
  store ptr %v3107, ptr %v3225, align 8, !tbaa !3
  %v3226 = getelementptr i8, ptr %v3215, i64 104
  store ptr %arg, ptr %v3226, align 8, !tbaa !3
  %v3227 = call ptr @mlf_closure(ptr @mlf.code.3126, ptr %v3215)
  %v3228 = call ptr @mlf_prim2(i64 1, ptr %v3125, ptr %v3227)
  ret ptr %v3228
}

define private ptr @mlf.code.3050(ptr %env, ptr %arg) {
entry:
  %v3051 = getelementptr i8, ptr %env, i64 24
  %v3052 = load ptr, ptr %v3051, align 8, !tbaa !3
  %v3053 = getelementptr i8, ptr %env, i64 32
  %v3054 = load ptr, ptr %v3053, align 8, !tbaa !3
  %v3055 = getelementptr i8, ptr %env, i64 40
  %v3056 = load ptr, ptr %v3055, align 8, !tbaa !3
  %v3057 = getelementptr i8, ptr %env, i64 48
  %v3058 = load ptr, ptr %v3057, align 8, !tbaa !3
  %v3059 = getelementptr i8, ptr %env, i64 56
  %v3060 = load ptr, ptr %v3059, align 8, !tbaa !3
  %v3061 = getelementptr i8, ptr %env, i64 64
  %v3062 = load ptr, ptr %v3061, align 8, !tbaa !3
  %v3063 = getelementptr i8, ptr %env, i64 72
  %v3064 = load ptr, ptr %v3063, align 8, !tbaa !3
  %v3065 = getelementptr i8, ptr %env, i64 80
  %v3066 = load ptr, ptr %v3065, align 8, !tbaa !3
  %v3067 = getelementptr i8, ptr %env, i64 88
  %v3068 = load ptr, ptr %v3067, align 8, !tbaa !3
  %v3083 = call ptr @mlf_env_new(i64 2)
  %v3084 = getelementptr i8, ptr %v3083, i64 24
  store ptr %v3052, ptr %v3084, align 8, !tbaa !3
  %v3085 = getelementptr i8, ptr %v3083, i64 32
  store ptr %v3056, ptr %v3085, align 8, !tbaa !3
  %v3086 = call ptr @mlf_thunk(ptr @mlf.code.3069, ptr %v3083)
  %v3229 = call ptr @mlf_env_new(i64 10)
  %v3230 = getelementptr i8, ptr %v3229, i64 24
  store ptr %v3052, ptr %v3230, align 8, !tbaa !3
  %v3231 = getelementptr i8, ptr %v3229, i64 32
  store ptr %v3054, ptr %v3231, align 8, !tbaa !3
  %v3232 = getelementptr i8, ptr %v3229, i64 40
  store ptr %v3056, ptr %v3232, align 8, !tbaa !3
  %v3233 = getelementptr i8, ptr %v3229, i64 48
  store ptr %v3058, ptr %v3233, align 8, !tbaa !3
  %v3234 = getelementptr i8, ptr %v3229, i64 56
  store ptr %v3060, ptr %v3234, align 8, !tbaa !3
  %v3235 = getelementptr i8, ptr %v3229, i64 64
  store ptr %v3062, ptr %v3235, align 8, !tbaa !3
  %v3236 = getelementptr i8, ptr %v3229, i64 72
  store ptr %v3064, ptr %v3236, align 8, !tbaa !3
  %v3237 = getelementptr i8, ptr %v3229, i64 80
  store ptr %v3066, ptr %v3237, align 8, !tbaa !3
  %v3238 = getelementptr i8, ptr %v3229, i64 88
  store ptr %v3068, ptr %v3238, align 8, !tbaa !3
  %v3239 = getelementptr i8, ptr %v3229, i64 96
  store ptr %arg, ptr %v3239, align 8, !tbaa !3
  %v3240 = call ptr @mlf_closure(ptr @mlf.code.3087, ptr %v3229)
  %v3241 = call ptr @mlf_prim2(i64 1, ptr %v3086, ptr %v3240)
  ret ptr %v3241
}

define private ptr @mlf.code.3015(ptr %env, ptr %arg) {
entry:
  %v3016 = getelementptr i8, ptr %env, i64 24
  %v3017 = load ptr, ptr %v3016, align 8, !tbaa !3
  %v3018 = getelementptr i8, ptr %env, i64 32
  %v3019 = load ptr, ptr %v3018, align 8, !tbaa !3
  %v3020 = getelementptr i8, ptr %env, i64 40
  %v3021 = load ptr, ptr %v3020, align 8, !tbaa !3
  %v3022 = getelementptr i8, ptr %env, i64 48
  %v3023 = load ptr, ptr %v3022, align 8, !tbaa !3
  %v3024 = getelementptr i8, ptr %env, i64 56
  %v3025 = load ptr, ptr %v3024, align 8, !tbaa !3
  %v3026 = getelementptr i8, ptr %env, i64 64
  %v3027 = load ptr, ptr %v3026, align 8, !tbaa !3
  %v3028 = getelementptr i8, ptr %env, i64 72
  %v3029 = load ptr, ptr %v3028, align 8, !tbaa !3
  %v3030 = getelementptr i8, ptr %env, i64 80
  %v3031 = load ptr, ptr %v3030, align 8, !tbaa !3
  %v3046 = call ptr @mlf_env_new(i64 2)
  %v3047 = getelementptr i8, ptr %v3046, i64 24
  store ptr %v3017, ptr %v3047, align 8, !tbaa !3
  %v3048 = getelementptr i8, ptr %v3046, i64 32
  store ptr %v3021, ptr %v3048, align 8, !tbaa !3
  %v3049 = call ptr @mlf_thunk(ptr @mlf.code.3032, ptr %v3046)
  %v3242 = call ptr @mlf_env_new(i64 9)
  %v3243 = getelementptr i8, ptr %v3242, i64 24
  store ptr %v3017, ptr %v3243, align 8, !tbaa !3
  %v3244 = getelementptr i8, ptr %v3242, i64 32
  store ptr %v3019, ptr %v3244, align 8, !tbaa !3
  %v3245 = getelementptr i8, ptr %v3242, i64 40
  store ptr %v3021, ptr %v3245, align 8, !tbaa !3
  %v3246 = getelementptr i8, ptr %v3242, i64 48
  store ptr %v3023, ptr %v3246, align 8, !tbaa !3
  %v3247 = getelementptr i8, ptr %v3242, i64 56
  store ptr %v3025, ptr %v3247, align 8, !tbaa !3
  %v3248 = getelementptr i8, ptr %v3242, i64 64
  store ptr %v3027, ptr %v3248, align 8, !tbaa !3
  %v3249 = getelementptr i8, ptr %v3242, i64 72
  store ptr %v3029, ptr %v3249, align 8, !tbaa !3
  %v3250 = getelementptr i8, ptr %v3242, i64 80
  store ptr %v3031, ptr %v3250, align 8, !tbaa !3
  %v3251 = getelementptr i8, ptr %v3242, i64 88
  store ptr %arg, ptr %v3251, align 8, !tbaa !3
  %v3252 = call ptr @mlf_closure(ptr @mlf.code.3050, ptr %v3242)
  %v3253 = call ptr @mlf_prim2(i64 1, ptr %v3049, ptr %v3252)
  ret ptr %v3253
}

define private ptr @mlf.code.2982(ptr %env, ptr %arg) {
entry:
  %v2983 = getelementptr i8, ptr %env, i64 24
  %v2984 = load ptr, ptr %v2983, align 8, !tbaa !3
  %v2985 = getelementptr i8, ptr %env, i64 32
  %v2986 = load ptr, ptr %v2985, align 8, !tbaa !3
  %v2987 = getelementptr i8, ptr %env, i64 40
  %v2988 = load ptr, ptr %v2987, align 8, !tbaa !3
  %v2989 = getelementptr i8, ptr %env, i64 48
  %v2990 = load ptr, ptr %v2989, align 8, !tbaa !3
  %v2991 = getelementptr i8, ptr %env, i64 56
  %v2992 = load ptr, ptr %v2991, align 8, !tbaa !3
  %v2993 = getelementptr i8, ptr %env, i64 64
  %v2994 = load ptr, ptr %v2993, align 8, !tbaa !3
  %v2995 = getelementptr i8, ptr %env, i64 72
  %v2996 = load ptr, ptr %v2995, align 8, !tbaa !3
  %v3011 = call ptr @mlf_env_new(i64 2)
  %v3012 = getelementptr i8, ptr %v3011, i64 24
  store ptr %v2984, ptr %v3012, align 8, !tbaa !3
  %v3013 = getelementptr i8, ptr %v3011, i64 32
  store ptr %v2988, ptr %v3013, align 8, !tbaa !3
  %v3014 = call ptr @mlf_thunk(ptr @mlf.code.2997, ptr %v3011)
  %v3254 = call ptr @mlf_env_new(i64 8)
  %v3255 = getelementptr i8, ptr %v3254, i64 24
  store ptr %v2984, ptr %v3255, align 8, !tbaa !3
  %v3256 = getelementptr i8, ptr %v3254, i64 32
  store ptr %v2986, ptr %v3256, align 8, !tbaa !3
  %v3257 = getelementptr i8, ptr %v3254, i64 40
  store ptr %v2988, ptr %v3257, align 8, !tbaa !3
  %v3258 = getelementptr i8, ptr %v3254, i64 48
  store ptr %v2990, ptr %v3258, align 8, !tbaa !3
  %v3259 = getelementptr i8, ptr %v3254, i64 56
  store ptr %v2992, ptr %v3259, align 8, !tbaa !3
  %v3260 = getelementptr i8, ptr %v3254, i64 64
  store ptr %v2994, ptr %v3260, align 8, !tbaa !3
  %v3261 = getelementptr i8, ptr %v3254, i64 72
  store ptr %v2996, ptr %v3261, align 8, !tbaa !3
  %v3262 = getelementptr i8, ptr %v3254, i64 80
  store ptr %arg, ptr %v3262, align 8, !tbaa !3
  %v3263 = call ptr @mlf_closure(ptr @mlf.code.3015, ptr %v3254)
  %v3264 = call ptr @mlf_prim2(i64 1, ptr %v3014, ptr %v3263)
  ret ptr %v3264
}

define private ptr @mlf.code.2951(ptr %env, ptr %arg) {
entry:
  %v2952 = getelementptr i8, ptr %env, i64 24
  %v2953 = load ptr, ptr %v2952, align 8, !tbaa !3
  %v2954 = getelementptr i8, ptr %env, i64 32
  %v2955 = load ptr, ptr %v2954, align 8, !tbaa !3
  %v2956 = getelementptr i8, ptr %env, i64 40
  %v2957 = load ptr, ptr %v2956, align 8, !tbaa !3
  %v2958 = getelementptr i8, ptr %env, i64 48
  %v2959 = load ptr, ptr %v2958, align 8, !tbaa !3
  %v2960 = getelementptr i8, ptr %env, i64 56
  %v2961 = load ptr, ptr %v2960, align 8, !tbaa !3
  %v2962 = getelementptr i8, ptr %env, i64 64
  %v2963 = load ptr, ptr %v2962, align 8, !tbaa !3
  %v2978 = call ptr @mlf_env_new(i64 2)
  %v2979 = getelementptr i8, ptr %v2978, i64 24
  store ptr %v2953, ptr %v2979, align 8, !tbaa !3
  %v2980 = getelementptr i8, ptr %v2978, i64 32
  store ptr %v2955, ptr %v2980, align 8, !tbaa !3
  %v2981 = call ptr @mlf_thunk(ptr @mlf.code.2964, ptr %v2978)
  %v3265 = call ptr @mlf_env_new(i64 7)
  %v3266 = getelementptr i8, ptr %v3265, i64 24
  store ptr %v2953, ptr %v3266, align 8, !tbaa !3
  %v3267 = getelementptr i8, ptr %v3265, i64 32
  store ptr %v2955, ptr %v3267, align 8, !tbaa !3
  %v3268 = getelementptr i8, ptr %v3265, i64 40
  store ptr %v2957, ptr %v3268, align 8, !tbaa !3
  %v3269 = getelementptr i8, ptr %v3265, i64 48
  store ptr %v2959, ptr %v3269, align 8, !tbaa !3
  %v3270 = getelementptr i8, ptr %v3265, i64 56
  store ptr %v2961, ptr %v3270, align 8, !tbaa !3
  %v3271 = getelementptr i8, ptr %v3265, i64 64
  store ptr %v2963, ptr %v3271, align 8, !tbaa !3
  %v3272 = getelementptr i8, ptr %v3265, i64 72
  store ptr %arg, ptr %v3272, align 8, !tbaa !3
  %v3273 = call ptr @mlf_closure(ptr @mlf.code.2982, ptr %v3265)
  %v3274 = call ptr @mlf_prim2(i64 1, ptr %v2981, ptr %v3273)
  ret ptr %v3274
}

define private ptr @mlf.code.2922(ptr %env, ptr %arg) {
entry:
  %v2923 = getelementptr i8, ptr %env, i64 24
  %v2924 = load ptr, ptr %v2923, align 8, !tbaa !3
  %v2925 = getelementptr i8, ptr %env, i64 32
  %v2926 = load ptr, ptr %v2925, align 8, !tbaa !3
  %v2927 = getelementptr i8, ptr %env, i64 40
  %v2928 = load ptr, ptr %v2927, align 8, !tbaa !3
  %v2929 = getelementptr i8, ptr %env, i64 48
  %v2930 = load ptr, ptr %v2929, align 8, !tbaa !3
  %v2931 = getelementptr i8, ptr %env, i64 56
  %v2932 = load ptr, ptr %v2931, align 8, !tbaa !3
  %v2947 = call ptr @mlf_env_new(i64 2)
  %v2948 = getelementptr i8, ptr %v2947, i64 24
  store ptr %v2924, ptr %v2948, align 8, !tbaa !3
  %v2949 = getelementptr i8, ptr %v2947, i64 32
  store ptr %v2926, ptr %v2949, align 8, !tbaa !3
  %v2950 = call ptr @mlf_thunk(ptr @mlf.code.2933, ptr %v2947)
  %v3275 = call ptr @mlf_env_new(i64 6)
  %v3276 = getelementptr i8, ptr %v3275, i64 24
  store ptr %v2924, ptr %v3276, align 8, !tbaa !3
  %v3277 = getelementptr i8, ptr %v3275, i64 32
  store ptr %v2926, ptr %v3277, align 8, !tbaa !3
  %v3278 = getelementptr i8, ptr %v3275, i64 40
  store ptr %v2928, ptr %v3278, align 8, !tbaa !3
  %v3279 = getelementptr i8, ptr %v3275, i64 48
  store ptr %v2930, ptr %v3279, align 8, !tbaa !3
  %v3280 = getelementptr i8, ptr %v3275, i64 56
  store ptr %v2932, ptr %v3280, align 8, !tbaa !3
  %v3281 = getelementptr i8, ptr %v3275, i64 64
  store ptr %arg, ptr %v3281, align 8, !tbaa !3
  %v3282 = call ptr @mlf_closure(ptr @mlf.code.2951, ptr %v3275)
  %v3283 = call ptr @mlf_prim2(i64 1, ptr %v2950, ptr %v3282)
  ret ptr %v3283
}

define private ptr @mlf.code.2895(ptr %env, ptr %arg) {
entry:
  %v2896 = getelementptr i8, ptr %env, i64 24
  %v2897 = load ptr, ptr %v2896, align 8, !tbaa !3
  %v2898 = getelementptr i8, ptr %env, i64 32
  %v2899 = load ptr, ptr %v2898, align 8, !tbaa !3
  %v2900 = getelementptr i8, ptr %env, i64 40
  %v2901 = load ptr, ptr %v2900, align 8, !tbaa !3
  %v2902 = getelementptr i8, ptr %env, i64 48
  %v2903 = load ptr, ptr %v2902, align 8, !tbaa !3
  %v2918 = call ptr @mlf_env_new(i64 2)
  %v2919 = getelementptr i8, ptr %v2918, i64 24
  store ptr %v2897, ptr %v2919, align 8, !tbaa !3
  %v2920 = getelementptr i8, ptr %v2918, i64 32
  store ptr %v2899, ptr %v2920, align 8, !tbaa !3
  %v2921 = call ptr @mlf_thunk(ptr @mlf.code.2904, ptr %v2918)
  %v3284 = call ptr @mlf_env_new(i64 5)
  %v3285 = getelementptr i8, ptr %v3284, i64 24
  store ptr %v2897, ptr %v3285, align 8, !tbaa !3
  %v3286 = getelementptr i8, ptr %v3284, i64 32
  store ptr %v2899, ptr %v3286, align 8, !tbaa !3
  %v3287 = getelementptr i8, ptr %v3284, i64 40
  store ptr %v2901, ptr %v3287, align 8, !tbaa !3
  %v3288 = getelementptr i8, ptr %v3284, i64 48
  store ptr %v2903, ptr %v3288, align 8, !tbaa !3
  %v3289 = getelementptr i8, ptr %v3284, i64 56
  store ptr %arg, ptr %v3289, align 8, !tbaa !3
  %v3290 = call ptr @mlf_closure(ptr @mlf.code.2922, ptr %v3284)
  %v3291 = call ptr @mlf_prim2(i64 1, ptr %v2921, ptr %v3290)
  ret ptr %v3291
}

define private ptr @mlf.worker.16(ptr %a0, ptr %a1, ptr %a2, ptr %a3) {
entry:
  %v2871 = call ptr @mlf_prim2(i64 10, ptr %a2, ptr inttoptr (i64 71 to ptr))
  %v2872 = icmp eq ptr %v2871, inttoptr (i64 6 to ptr)
  br i1 %v2872, label %yes.2873, label %no.2874
yes.2873:
  %v2876 = call ptr @mlf_prim1(i64 0, ptr %a3)
  br label %join.2875
no.2874:
  %v2891 = call ptr @mlf_env_new(i64 2)
  %v2892 = getelementptr i8, ptr %v2891, i64 24
  store ptr %a0, ptr %v2892, align 8, !tbaa !3
  %v2893 = getelementptr i8, ptr %v2891, i64 32
  store ptr %a1, ptr %v2893, align 8, !tbaa !3
  %v2894 = call ptr @mlf_thunk(ptr @mlf.code.2877, ptr %v2891)
  %v3292 = call ptr @mlf_env_new(i64 4)
  %v3293 = getelementptr i8, ptr %v3292, i64 24
  store ptr %a0, ptr %v3293, align 8, !tbaa !3
  %v3294 = getelementptr i8, ptr %v3292, i64 32
  store ptr %a1, ptr %v3294, align 8, !tbaa !3
  %v3295 = getelementptr i8, ptr %v3292, i64 40
  store ptr %a2, ptr %v3295, align 8, !tbaa !3
  %v3296 = getelementptr i8, ptr %v3292, i64 48
  store ptr %a3, ptr %v3296, align 8, !tbaa !3
  %v3297 = call ptr @mlf_closure(ptr @mlf.code.2895, ptr %v3292)
  %v3298 = call ptr @mlf_prim2(i64 1, ptr %v2894, ptr %v3297)
  br label %join.2875
join.2875:
  %v3299 = phi ptr [ %v2876, %yes.2873 ], [ %v3298, %no.2874 ]
  ret ptr %v3299
}

define private ptr @mlf.numeric.entry.2696(ptr %env, ptr %arg) {
entry:
  %v2697 = getelementptr i8, ptr %env, i64 24
  %v2698 = load ptr, ptr %v2697, align 8, !tbaa !3
  %v2699 = getelementptr i8, ptr %env, i64 32
  %v2700 = load ptr, ptr %v2699, align 8, !tbaa !3
  %v2701 = getelementptr i8, ptr %env, i64 40
  %v2702 = load ptr, ptr %v2701, align 8, !tbaa !3
  %v2703 = getelementptr i8, ptr %env, i64 48
  %v2704 = load ptr, ptr %v2703, align 8, !tbaa !3
  %v2705 = call ptr @mlf_peek(ptr %v2698)
  %v2706 = call ptr @mlf_peek(ptr %v2700)
  %v2707 = call ptr @mlf_peek(ptr %v2702)
  %v2708 = call ptr @mlf_peek(ptr %v2704)
  %v2709 = icmp ne ptr %v2705, null
  %v2710 = icmp ne ptr %v2706, null
  %v2711 = icmp ne ptr %v2707, null
  %v2712 = icmp ne ptr %v2708, null
  %v2713 = and i1 true, %v2709
  %v2714 = and i1 %v2713, %v2710
  %v2715 = and i1 %v2714, %v2711
  %v2716 = and i1 %v2715, %v2712
  br i1 %v2716, label %yes.2717, label %no.2718
yes.2717:
  %v2869 = call ptr @mlf.numeric.16(ptr %v2705, ptr %v2706, ptr %v2707, ptr %v2708)
  %v2870 = call ptr @mlf_prim1(i64 0, ptr %v2869)
  br label %join.2719
no.2718:
  %v3300 = call ptr @mlf_force(ptr %v2702)
  %v3301 = call ptr @mlf.worker.16(ptr %v2698, ptr %v2700, ptr %v3300, ptr %v2704)
  br label %join.2719
join.2719:
  %v3302 = phi ptr [ %v2870, %yes.2717 ], [ %v3301, %no.2718 ]
  ret ptr %v3302
}

define private ptr @mlf.code.3305(ptr %env, ptr %arg) {
entry:
  %v3306 = getelementptr i8, ptr %env, i64 24
  %v3307 = load ptr, ptr %v3306, align 8, !tbaa !3
  %v3308 = getelementptr i8, ptr %env, i64 32
  %v3309 = load ptr, ptr %v3308, align 8, !tbaa !3
  %v3310 = getelementptr i8, ptr %env, i64 40
  %v3311 = load ptr, ptr %v3310, align 8, !tbaa !3
  %v3312 = getelementptr i8, ptr %env, i64 48
  %v3313 = load ptr, ptr %v3312, align 8, !tbaa !3
  %v3314 = getelementptr i8, ptr %env, i64 56
  %v3315 = load ptr, ptr %v3314, align 8, !tbaa !3
  %v3316 = call ptr @mlf_force(ptr %v3307)
  %v3317 = call ptr @mlf_double(double 0x3fe0000000000000)
  %v3318 = call ptr @mlf_force(ptr %v3315)
  %v3319 = call ptr @mlf_prim2(i64 20, ptr %v3317, ptr %v3318)
  %v3320 = call ptr @mlf_force(ptr %v3309)
  %v3321 = call ptr @mlf_prim2(i64 20, ptr %v3320, ptr %v3320)
  %v3322 = call ptr @mlf_force(ptr %v3311)
  %v3323 = call ptr @mlf_prim2(i64 20, ptr %v3322, ptr %v3322)
  %v3324 = call ptr @mlf_prim2(i64 18, ptr %v3321, ptr %v3323)
  %v3325 = call ptr @mlf_force(ptr %v3313)
  %v3326 = call ptr @mlf_prim2(i64 20, ptr %v3325, ptr %v3325)
  %v3327 = call ptr @mlf_prim2(i64 18, ptr %v3324, ptr %v3326)
  %v3328 = call ptr @mlf_prim2(i64 20, ptr %v3319, ptr %v3327)
  %v3329 = call ptr @mlf_prim2(i64 18, ptr %v3316, ptr %v3328)
  ret ptr %v3329
}

define private ptr @mlf.code.2681(ptr %env, ptr %arg) {
entry:
  %v2682 = getelementptr i8, ptr %env, i64 24
  %v2683 = load ptr, ptr %v2682, align 8, !tbaa !3
  %v2684 = getelementptr i8, ptr %env, i64 32
  %v2685 = load ptr, ptr %v2684, align 8, !tbaa !3
  %v2686 = getelementptr i8, ptr %env, i64 40
  %v2687 = load ptr, ptr %v2686, align 8, !tbaa !3
  %v2688 = getelementptr i8, ptr %env, i64 48
  %v2689 = load ptr, ptr %v2688, align 8, !tbaa !3
  %v2690 = getelementptr i8, ptr %env, i64 56
  %v2691 = load ptr, ptr %v2690, align 8, !tbaa !3
  %v2692 = getelementptr i8, ptr %env, i64 64
  %v2693 = load ptr, ptr %v2692, align 8, !tbaa !3
  %v2694 = getelementptr i8, ptr %env, i64 72
  %v2695 = load ptr, ptr %v2694, align 8, !tbaa !3
  %v3303 = call ptr @mlf_force(ptr %v2685)
  %v3304 = call ptr @mlf_prim2(i64 8, ptr %v3303, ptr inttoptr (i64 15 to ptr))
  %v3330 = call ptr @mlf_env_new(i64 5)
  %v3331 = getelementptr i8, ptr %v3330, i64 24
  store ptr %v2687, ptr %v3331, align 8, !tbaa !3
  %v3332 = getelementptr i8, ptr %v3330, i64 32
  store ptr %v2689, ptr %v3332, align 8, !tbaa !3
  %v3333 = getelementptr i8, ptr %v3330, i64 40
  store ptr %v2691, ptr %v3333, align 8, !tbaa !3
  %v3334 = getelementptr i8, ptr %v3330, i64 48
  store ptr %v2693, ptr %v3334, align 8, !tbaa !3
  %v3335 = getelementptr i8, ptr %v3330, i64 56
  store ptr %v2695, ptr %v3335, align 8, !tbaa !3
  %v3336 = call ptr @mlf_thunk(ptr @mlf.code.3305, ptr %v3330)
  %v3337 = call ptr @mlf_env_new(i64 4)
  %v3338 = getelementptr i8, ptr %v3337, i64 24
  store ptr %v2683, ptr %v3338, align 8, !tbaa !3
  %v3339 = getelementptr i8, ptr %v3337, i64 32
  store ptr %v2685, ptr %v3339, align 8, !tbaa !3
  %v3340 = getelementptr i8, ptr %v3337, i64 40
  store ptr %v3304, ptr %v3340, align 8, !tbaa !3
  %v3341 = getelementptr i8, ptr %v3337, i64 48
  store ptr %v3336, ptr %v3341, align 8, !tbaa !3
  %v3342 = call ptr @mlf_native_io(ptr @mlf.numeric.entry.2696, ptr %v3337)
  ret ptr %v3342
}

define private ptr @mlf.code.3352(ptr %env, ptr %arg) {
entry:
  %v3353 = getelementptr i8, ptr %env, i64 24
  %v3354 = load ptr, ptr %v3353, align 8, !tbaa !3
  %v3355 = getelementptr i8, ptr %env, i64 32
  %v3356 = load ptr, ptr %v3355, align 8, !tbaa !3
  %v3357 = call ptr @mlf_force(ptr %v3356)
  %v3358 = call ptr @mlf_prim2(i64 8, ptr %v3357, ptr inttoptr (i64 15 to ptr))
  %v3359 = call ptr @mlf_env_new(i64 3)
  %v3360 = getelementptr i8, ptr %v3359, i64 24
  store ptr %v3354, ptr %v3360, align 8, !tbaa !3
  %v3361 = getelementptr i8, ptr %v3359, i64 32
  store ptr %v3358, ptr %v3361, align 8, !tbaa !3
  %v3362 = getelementptr i8, ptr %v3359, i64 40
  store ptr %arg, ptr %v3362, align 8, !tbaa !3
  %v3363 = call ptr @mlf_native_io(ptr @mlf.numeric.entry.2203, ptr %v3359)
  ret ptr %v3363
}

define private ptr @mlf.code.2668(ptr %env, ptr %arg) {
entry:
  %v2669 = getelementptr i8, ptr %env, i64 24
  %v2670 = load ptr, ptr %v2669, align 8, !tbaa !3
  %v2671 = getelementptr i8, ptr %env, i64 32
  %v2672 = load ptr, ptr %v2671, align 8, !tbaa !3
  %v2673 = getelementptr i8, ptr %env, i64 40
  %v2674 = load ptr, ptr %v2673, align 8, !tbaa !3
  %v2675 = getelementptr i8, ptr %env, i64 48
  %v2676 = load ptr, ptr %v2675, align 8, !tbaa !3
  %v2677 = getelementptr i8, ptr %env, i64 56
  %v2678 = load ptr, ptr %v2677, align 8, !tbaa !3
  %v2679 = getelementptr i8, ptr %env, i64 64
  %v2680 = load ptr, ptr %v2679, align 8, !tbaa !3
  %v3343 = call ptr @mlf_env_new(i64 7)
  %v3344 = getelementptr i8, ptr %v3343, i64 24
  store ptr %v2670, ptr %v3344, align 8, !tbaa !3
  %v3345 = getelementptr i8, ptr %v3343, i64 32
  store ptr %v2672, ptr %v3345, align 8, !tbaa !3
  %v3346 = getelementptr i8, ptr %v3343, i64 40
  store ptr %v2674, ptr %v3346, align 8, !tbaa !3
  %v3347 = getelementptr i8, ptr %v3343, i64 48
  store ptr %v2676, ptr %v3347, align 8, !tbaa !3
  %v3348 = getelementptr i8, ptr %v3343, i64 56
  store ptr %v2678, ptr %v3348, align 8, !tbaa !3
  %v3349 = getelementptr i8, ptr %v3343, i64 64
  store ptr %v2680, ptr %v3349, align 8, !tbaa !3
  %v3350 = getelementptr i8, ptr %v3343, i64 72
  store ptr %arg, ptr %v3350, align 8, !tbaa !3
  %v3351 = call ptr @mlf_thunk(ptr @mlf.code.2681, ptr %v3343)
  %v3364 = call ptr @mlf_env_new(i64 2)
  %v3365 = getelementptr i8, ptr %v3364, i64 24
  store ptr %v2670, ptr %v3365, align 8, !tbaa !3
  %v3366 = getelementptr i8, ptr %v3364, i64 32
  store ptr %v2672, ptr %v3366, align 8, !tbaa !3
  %v3367 = call ptr @mlf_closure(ptr @mlf.code.3352, ptr %v3364)
  %v3368 = call ptr @mlf_prim2(i64 1, ptr %v3351, ptr %v3367)
  ret ptr %v3368
}

define private ptr @mlf.code.2639(ptr %env, ptr %arg) {
entry:
  %v2640 = getelementptr i8, ptr %env, i64 24
  %v2641 = load ptr, ptr %v2640, align 8, !tbaa !3
  %v2642 = getelementptr i8, ptr %env, i64 32
  %v2643 = load ptr, ptr %v2642, align 8, !tbaa !3
  %v2644 = getelementptr i8, ptr %env, i64 40
  %v2645 = load ptr, ptr %v2644, align 8, !tbaa !3
  %v2646 = getelementptr i8, ptr %env, i64 48
  %v2647 = load ptr, ptr %v2646, align 8, !tbaa !3
  %v2648 = getelementptr i8, ptr %env, i64 56
  %v2649 = load ptr, ptr %v2648, align 8, !tbaa !3
  %v2664 = call ptr @mlf_env_new(i64 2)
  %v2665 = getelementptr i8, ptr %v2664, i64 24
  store ptr %v2641, ptr %v2665, align 8, !tbaa !3
  %v2666 = getelementptr i8, ptr %v2664, i64 32
  store ptr %v2643, ptr %v2666, align 8, !tbaa !3
  %v2667 = call ptr @mlf_thunk(ptr @mlf.code.2650, ptr %v2664)
  %v3369 = call ptr @mlf_env_new(i64 6)
  %v3370 = getelementptr i8, ptr %v3369, i64 24
  store ptr %v2641, ptr %v3370, align 8, !tbaa !3
  %v3371 = getelementptr i8, ptr %v3369, i64 32
  store ptr %v2643, ptr %v3371, align 8, !tbaa !3
  %v3372 = getelementptr i8, ptr %v3369, i64 40
  store ptr %v2645, ptr %v3372, align 8, !tbaa !3
  %v3373 = getelementptr i8, ptr %v3369, i64 48
  store ptr %v2647, ptr %v3373, align 8, !tbaa !3
  %v3374 = getelementptr i8, ptr %v3369, i64 56
  store ptr %v2649, ptr %v3374, align 8, !tbaa !3
  %v3375 = getelementptr i8, ptr %v3369, i64 64
  store ptr %arg, ptr %v3375, align 8, !tbaa !3
  %v3376 = call ptr @mlf_closure(ptr @mlf.code.2668, ptr %v3369)
  %v3377 = call ptr @mlf_prim2(i64 1, ptr %v2667, ptr %v3376)
  ret ptr %v3377
}

define private ptr @mlf.code.2612(ptr %env, ptr %arg) {
entry:
  %v2613 = getelementptr i8, ptr %env, i64 24
  %v2614 = load ptr, ptr %v2613, align 8, !tbaa !3
  %v2615 = getelementptr i8, ptr %env, i64 32
  %v2616 = load ptr, ptr %v2615, align 8, !tbaa !3
  %v2617 = getelementptr i8, ptr %env, i64 40
  %v2618 = load ptr, ptr %v2617, align 8, !tbaa !3
  %v2619 = getelementptr i8, ptr %env, i64 48
  %v2620 = load ptr, ptr %v2619, align 8, !tbaa !3
  %v2635 = call ptr @mlf_env_new(i64 2)
  %v2636 = getelementptr i8, ptr %v2635, i64 24
  store ptr %v2614, ptr %v2636, align 8, !tbaa !3
  %v2637 = getelementptr i8, ptr %v2635, i64 32
  store ptr %v2616, ptr %v2637, align 8, !tbaa !3
  %v2638 = call ptr @mlf_thunk(ptr @mlf.code.2621, ptr %v2635)
  %v3378 = call ptr @mlf_env_new(i64 5)
  %v3379 = getelementptr i8, ptr %v3378, i64 24
  store ptr %v2614, ptr %v3379, align 8, !tbaa !3
  %v3380 = getelementptr i8, ptr %v3378, i64 32
  store ptr %v2616, ptr %v3380, align 8, !tbaa !3
  %v3381 = getelementptr i8, ptr %v3378, i64 40
  store ptr %v2618, ptr %v3381, align 8, !tbaa !3
  %v3382 = getelementptr i8, ptr %v3378, i64 48
  store ptr %v2620, ptr %v3382, align 8, !tbaa !3
  %v3383 = getelementptr i8, ptr %v3378, i64 56
  store ptr %arg, ptr %v3383, align 8, !tbaa !3
  %v3384 = call ptr @mlf_closure(ptr @mlf.code.2639, ptr %v3378)
  %v3385 = call ptr @mlf_prim2(i64 1, ptr %v2638, ptr %v3384)
  ret ptr %v3385
}

define private ptr @mlf.code.2587(ptr %env, ptr %arg) {
entry:
  %v2588 = getelementptr i8, ptr %env, i64 24
  %v2589 = load ptr, ptr %v2588, align 8, !tbaa !3
  %v2590 = getelementptr i8, ptr %env, i64 32
  %v2591 = load ptr, ptr %v2590, align 8, !tbaa !3
  %v2592 = getelementptr i8, ptr %env, i64 40
  %v2593 = load ptr, ptr %v2592, align 8, !tbaa !3
  %v2608 = call ptr @mlf_env_new(i64 2)
  %v2609 = getelementptr i8, ptr %v2608, i64 24
  store ptr %v2589, ptr %v2609, align 8, !tbaa !3
  %v2610 = getelementptr i8, ptr %v2608, i64 32
  store ptr %v2591, ptr %v2610, align 8, !tbaa !3
  %v2611 = call ptr @mlf_thunk(ptr @mlf.code.2594, ptr %v2608)
  %v3386 = call ptr @mlf_env_new(i64 4)
  %v3387 = getelementptr i8, ptr %v3386, i64 24
  store ptr %v2589, ptr %v3387, align 8, !tbaa !3
  %v3388 = getelementptr i8, ptr %v3386, i64 32
  store ptr %v2591, ptr %v3388, align 8, !tbaa !3
  %v3389 = getelementptr i8, ptr %v3386, i64 40
  store ptr %v2593, ptr %v3389, align 8, !tbaa !3
  %v3390 = getelementptr i8, ptr %v3386, i64 48
  store ptr %arg, ptr %v3390, align 8, !tbaa !3
  %v3391 = call ptr @mlf_closure(ptr @mlf.code.2612, ptr %v3386)
  %v3392 = call ptr @mlf_prim2(i64 1, ptr %v2611, ptr %v3391)
  ret ptr %v3392
}

define private ptr @mlf.worker.33(ptr %a0, ptr %a1, ptr %a2) {
entry:
  %v2563 = call ptr @mlf_prim2(i64 10, ptr %a1, ptr inttoptr (i64 71 to ptr))
  %v2564 = icmp eq ptr %v2563, inttoptr (i64 6 to ptr)
  br i1 %v2564, label %yes.2565, label %no.2566
yes.2565:
  %v2568 = call ptr @mlf_prim1(i64 0, ptr %a2)
  br label %join.2567
no.2566:
  %v2583 = call ptr @mlf_env_new(i64 2)
  %v2584 = getelementptr i8, ptr %v2583, i64 24
  store ptr %a0, ptr %v2584, align 8, !tbaa !3
  %v2585 = getelementptr i8, ptr %v2583, i64 32
  store ptr %a1, ptr %v2585, align 8, !tbaa !3
  %v2586 = call ptr @mlf_thunk(ptr @mlf.code.2569, ptr %v2583)
  %v3393 = call ptr @mlf_env_new(i64 3)
  %v3394 = getelementptr i8, ptr %v3393, i64 24
  store ptr %a0, ptr %v3394, align 8, !tbaa !3
  %v3395 = getelementptr i8, ptr %v3393, i64 32
  store ptr %a1, ptr %v3395, align 8, !tbaa !3
  %v3396 = getelementptr i8, ptr %v3393, i64 40
  store ptr %a2, ptr %v3396, align 8, !tbaa !3
  %v3397 = call ptr @mlf_closure(ptr @mlf.code.2587, ptr %v3393)
  %v3398 = call ptr @mlf_prim2(i64 1, ptr %v2586, ptr %v3397)
  br label %join.2567
join.2567:
  %v3399 = phi ptr [ %v2568, %yes.2565 ], [ %v3398, %no.2566 ]
  ret ptr %v3399
}

define private ptr @mlf.numeric.entry.2203(ptr %env, ptr %arg) {
entry:
  %v2204 = getelementptr i8, ptr %env, i64 24
  %v2205 = load ptr, ptr %v2204, align 8, !tbaa !3
  %v2206 = getelementptr i8, ptr %env, i64 32
  %v2207 = load ptr, ptr %v2206, align 8, !tbaa !3
  %v2208 = getelementptr i8, ptr %env, i64 40
  %v2209 = load ptr, ptr %v2208, align 8, !tbaa !3
  %v2210 = call ptr @mlf_peek(ptr %v2205)
  %v2211 = call ptr @mlf_peek(ptr %v2207)
  %v2212 = call ptr @mlf_peek(ptr %v2209)
  %v2213 = icmp ne ptr %v2210, null
  %v2214 = icmp ne ptr %v2211, null
  %v2215 = icmp ne ptr %v2212, null
  %v2216 = and i1 true, %v2213
  %v2217 = and i1 %v2216, %v2214
  %v2218 = and i1 %v2217, %v2215
  br i1 %v2218, label %yes.2219, label %no.2220
yes.2219:
  %v2561 = call ptr @mlf.numeric.33(ptr %v2210, ptr %v2211, ptr %v2212)
  %v2562 = call ptr @mlf_prim1(i64 0, ptr %v2561)
  br label %join.2221
no.2220:
  %v3400 = call ptr @mlf_force(ptr %v2207)
  %v3401 = call ptr @mlf.worker.33(ptr %v2205, ptr %v3400, ptr %v2209)
  br label %join.2221
join.2221:
  %v3402 = phi ptr [ %v2562, %yes.2219 ], [ %v3401, %no.2220 ]
  ret ptr %v3402
}

define private ptr @mlf.code.2200(ptr %env, ptr %arg) {
entry:
  %v2201 = getelementptr i8, ptr %env, i64 24
  %v2202 = load ptr, ptr %v2201, align 8, !tbaa !3
  %v3403 = call ptr @mlf_double(double 0x0000000000000000)
  %v3404 = call ptr @mlf_env_new(i64 3)
  %v3405 = getelementptr i8, ptr %v3404, i64 24
  store ptr %v2202, ptr %v3405, align 8, !tbaa !3
  %v3406 = getelementptr i8, ptr %v3404, i64 32
  store ptr inttoptr (i64 1 to ptr), ptr %v3406, align 8, !tbaa !3
  %v3407 = getelementptr i8, ptr %v3404, i64 40
  store ptr %v3403, ptr %v3407, align 8, !tbaa !3
  %v3408 = call ptr @mlf_native_io(ptr @mlf.numeric.entry.2203, ptr %v3404)
  ret ptr %v3408
}

define private ptr @mlf.code.3420(ptr %env, ptr %arg) {
entry:
  %v3421 = getelementptr i8, ptr %env, i64 24
  %v3422 = load ptr, ptr %v3421, align 8, !tbaa !3
  %v3423 = call ptr @mlf_force(ptr %v3422)
  %v3424 = call ptr @mlf_prim2(i64 26, ptr inttoptr (i64 19 to ptr), ptr %v3423)
  ret ptr %v3424
}

define private ptr @mlf.code.3417(ptr %env, ptr %arg) {
entry:
  %v3418 = getelementptr i8, ptr %env, i64 24
  %v3419 = load ptr, ptr %v3418, align 8, !tbaa !3
  %v3425 = call ptr @mlf_env_new(i64 1)
  %v3426 = getelementptr i8, ptr %v3425, i64 24
  store ptr %v3419, ptr %v3426, align 8, !tbaa !3
  %v3427 = call ptr @mlf_thunk(ptr @mlf.code.3420, ptr %v3425)
  %v3428 = call ptr @mlf_prim1(i64 3, ptr %v3427)
  ret ptr %v3428
}

define private ptr @mlf.numeric.42(ptr %a0, ptr %a1, ptr %a2) alwaysinline {
entry:
  %v3506 = ptrtoint ptr %a2 to i64
  %v3507 = ptrtoint ptr inttoptr (i64 71 to ptr) to i64
  %v3508 = and i64 %v3506, %v3507
  %v3509 = and i64 %v3508, 1
  %v3510 = icmp ne i64 %v3509, 0
  br i1 %v3510, label %yes.3511, label %no.3512
yes.3511:
  %v3514 = icmp eq i64 %v3506, %v3507
  %v3515 = select i1 %v3514, ptr inttoptr (i64 6 to ptr), ptr inttoptr (i64 2 to ptr)
  br label %join.3513
no.3512:
  %v3516 = call ptr @mlf_eq_int(ptr %a2, ptr inttoptr (i64 71 to ptr))
  br label %join.3513
join.3513:
  %v3517 = phi ptr [ %v3515, %yes.3511 ], [ %v3516, %no.3512 ]
  %v3518 = icmp eq ptr %v3517, inttoptr (i64 6 to ptr)
  br i1 %v3518, label %tail.yes.3519, label %tail.no.3520
tail.yes.3519:
  ret ptr inttoptr (i64 4 to ptr)
tail.no.3520:
  %v3521 = getelementptr i8, ptr %a0, i64 24
  %v3522 = load i64, ptr %v3521, align 8, !tbaa !3
  %v3523 = getelementptr i8, ptr %a0, i64 32
  %v3524 = load ptr, ptr %v3523, align 8, !tbaa !3
  %v3525 = ptrtoint ptr %a1 to i64
  %v3526 = ashr i64 %v3525, 1
  %v3527 = and i64 %v3525, 1
  %v3528 = icmp ne i64 %v3527, 0
  %v3529 = icmp ult i64 %v3526, %v3522
  %v3530 = and i1 %v3528, %v3529
  br i1 %v3530, label %array.valid.3531, label %array.invalid.3532
array.invalid.3532:
  call void @mlf_bounds_failure()
  unreachable
array.valid.3531:
  %v3533 = getelementptr i64, ptr %v3524, i64 %v3526
  %v3534 = load double, ptr %v3533, align 8, !tbaa !4
  %v3535 = ptrtoint ptr %a1 to i64
  %v3536 = ptrtoint ptr inttoptr (i64 3 to ptr) to i64
  %v3537 = sub i64 %v3536, 1
  %v3538 = add nsw i64 %v3535, %v3537
  %v3539 = inttoptr i64 %v3538 to ptr
  %v3540 = ptrtoint ptr %v3539 to i64
  %v3541 = ashr i64 %v3540, 1
  %v3542 = and i64 %v3540, 1
  %v3543 = icmp ne i64 %v3542, 0
  %v3544 = icmp ult i64 %v3541, %v3522
  %v3545 = and i1 %v3543, %v3544
  br i1 %v3545, label %array.valid.3546, label %array.invalid.3547
array.invalid.3547:
  call void @mlf_bounds_failure()
  unreachable
array.valid.3546:
  %v3548 = getelementptr i64, ptr %v3524, i64 %v3541
  %v3549 = load double, ptr %v3548, align 8, !tbaa !4
  %v3550 = ptrtoint ptr %a1 to i64
  %v3551 = ptrtoint ptr inttoptr (i64 5 to ptr) to i64
  %v3552 = sub i64 %v3551, 1
  %v3553 = add nsw i64 %v3550, %v3552
  %v3554 = inttoptr i64 %v3553 to ptr
  %v3555 = ptrtoint ptr %v3554 to i64
  %v3556 = ashr i64 %v3555, 1
  %v3557 = and i64 %v3555, 1
  %v3558 = icmp ne i64 %v3557, 0
  %v3559 = icmp ult i64 %v3556, %v3522
  %v3560 = and i1 %v3558, %v3559
  br i1 %v3560, label %array.valid.3561, label %array.invalid.3562
array.invalid.3562:
  call void @mlf_bounds_failure()
  unreachable
array.valid.3561:
  %v3563 = getelementptr i64, ptr %v3524, i64 %v3556
  %v3564 = load double, ptr %v3563, align 8, !tbaa !4
  %v3565 = ptrtoint ptr %a1 to i64
  %v3566 = ptrtoint ptr inttoptr (i64 13 to ptr) to i64
  %v3567 = sub i64 %v3566, 1
  %v3568 = add nsw i64 %v3565, %v3567
  %v3569 = inttoptr i64 %v3568 to ptr
  %v3570 = ptrtoint ptr %v3569 to i64
  %v3571 = ashr i64 %v3570, 1
  %v3572 = and i64 %v3570, 1
  %v3573 = icmp ne i64 %v3572, 0
  %v3574 = icmp ult i64 %v3571, %v3522
  %v3575 = and i1 %v3573, %v3574
  br i1 %v3575, label %array.valid.3576, label %array.invalid.3577
array.invalid.3577:
  call void @mlf_bounds_failure()
  unreachable
array.valid.3576:
  %v3578 = getelementptr i64, ptr %v3524, i64 %v3571
  %v3579 = load double, ptr %v3578, align 8, !tbaa !4
  %v3580 = ptrtoint ptr %a2 to i64
  %v3581 = ashr i64 %v3580, 1
  %v3582 = and i64 %v3580, 1
  %v3583 = icmp ne i64 %v3582, 0
  %v3584 = icmp ult i64 %v3581, %v3522
  %v3585 = and i1 %v3583, %v3584
  br i1 %v3585, label %array.valid.3586, label %array.invalid.3587
array.invalid.3587:
  call void @mlf_bounds_failure()
  unreachable
array.valid.3586:
  %v3588 = getelementptr i64, ptr %v3524, i64 %v3581
  %v3589 = load double, ptr %v3588, align 8, !tbaa !4
  %v3590 = ptrtoint ptr %a2 to i64
  %v3591 = ptrtoint ptr inttoptr (i64 3 to ptr) to i64
  %v3592 = sub i64 %v3591, 1
  %v3593 = add nsw i64 %v3590, %v3592
  %v3594 = inttoptr i64 %v3593 to ptr
  %v3595 = ptrtoint ptr %v3594 to i64
  %v3596 = ashr i64 %v3595, 1
  %v3597 = and i64 %v3595, 1
  %v3598 = icmp ne i64 %v3597, 0
  %v3599 = icmp ult i64 %v3596, %v3522
  %v3600 = and i1 %v3598, %v3599
  br i1 %v3600, label %array.valid.3601, label %array.invalid.3602
array.invalid.3602:
  call void @mlf_bounds_failure()
  unreachable
array.valid.3601:
  %v3603 = getelementptr i64, ptr %v3524, i64 %v3596
  %v3604 = load double, ptr %v3603, align 8, !tbaa !4
  %v3605 = ptrtoint ptr %a2 to i64
  %v3606 = ptrtoint ptr inttoptr (i64 5 to ptr) to i64
  %v3607 = sub i64 %v3606, 1
  %v3608 = add nsw i64 %v3605, %v3607
  %v3609 = inttoptr i64 %v3608 to ptr
  %v3610 = ptrtoint ptr %v3609 to i64
  %v3611 = ashr i64 %v3610, 1
  %v3612 = and i64 %v3610, 1
  %v3613 = icmp ne i64 %v3612, 0
  %v3614 = icmp ult i64 %v3611, %v3522
  %v3615 = and i1 %v3613, %v3614
  br i1 %v3615, label %array.valid.3616, label %array.invalid.3617
array.invalid.3617:
  call void @mlf_bounds_failure()
  unreachable
array.valid.3616:
  %v3618 = getelementptr i64, ptr %v3524, i64 %v3611
  %v3619 = load double, ptr %v3618, align 8, !tbaa !4
  %v3620 = ptrtoint ptr %a2 to i64
  %v3621 = ptrtoint ptr inttoptr (i64 13 to ptr) to i64
  %v3622 = sub i64 %v3621, 1
  %v3623 = add nsw i64 %v3620, %v3622
  %v3624 = inttoptr i64 %v3623 to ptr
  %v3625 = ptrtoint ptr %v3624 to i64
  %v3626 = ashr i64 %v3625, 1
  %v3627 = and i64 %v3625, 1
  %v3628 = icmp ne i64 %v3627, 0
  %v3629 = icmp ult i64 %v3626, %v3522
  %v3630 = and i1 %v3628, %v3629
  br i1 %v3630, label %array.valid.3631, label %array.invalid.3632
array.invalid.3632:
  call void @mlf_bounds_failure()
  unreachable
array.valid.3631:
  %v3633 = getelementptr i64, ptr %v3524, i64 %v3626
  %v3634 = load double, ptr %v3633, align 8, !tbaa !4
  %v3635 = fsub double %v3534, %v3589
  %v3636 = fsub double %v3549, %v3604
  %v3637 = fsub double %v3564, %v3619
  %v3638 = fmul double %v3635, %v3635
  %v3639 = fmul double %v3636, %v3636
  %v3640 = fadd double %v3638, %v3639
  %v3641 = fmul double %v3637, %v3637
  %v3642 = fadd double %v3640, %v3641
  %v3643 = call double @llvm.sqrt.f64(double %v3642)
  %v3644 = fmul double %v3643, %v3643
  %v3645 = fmul double %v3644, %v3643
  %v3646 = fdiv double 0x3f847ae147ae147b, %v3645
  %v3647 = ptrtoint ptr %a1 to i64
  %v3648 = ptrtoint ptr inttoptr (i64 7 to ptr) to i64
  %v3649 = sub i64 %v3648, 1
  %v3650 = add nsw i64 %v3647, %v3649
  %v3651 = inttoptr i64 %v3650 to ptr
  %v3652 = ptrtoint ptr %v3651 to i64
  %v3653 = ashr i64 %v3652, 1
  %v3654 = and i64 %v3652, 1
  %v3655 = icmp ne i64 %v3654, 0
  %v3656 = icmp ult i64 %v3653, %v3522
  %v3657 = and i1 %v3655, %v3656
  br i1 %v3657, label %array.valid.3658, label %array.invalid.3659
array.invalid.3659:
  call void @mlf_bounds_failure()
  unreachable
array.valid.3658:
  %v3660 = getelementptr i64, ptr %v3524, i64 %v3653
  %v3661 = load double, ptr %v3660, align 8, !tbaa !4
  %v3662 = ptrtoint ptr %a1 to i64
  %v3663 = ptrtoint ptr inttoptr (i64 9 to ptr) to i64
  %v3664 = sub i64 %v3663, 1
  %v3665 = add nsw i64 %v3662, %v3664
  %v3666 = inttoptr i64 %v3665 to ptr
  %v3667 = ptrtoint ptr %v3666 to i64
  %v3668 = ashr i64 %v3667, 1
  %v3669 = and i64 %v3667, 1
  %v3670 = icmp ne i64 %v3669, 0
  %v3671 = icmp ult i64 %v3668, %v3522
  %v3672 = and i1 %v3670, %v3671
  br i1 %v3672, label %array.valid.3673, label %array.invalid.3674
array.invalid.3674:
  call void @mlf_bounds_failure()
  unreachable
array.valid.3673:
  %v3675 = getelementptr i64, ptr %v3524, i64 %v3668
  %v3676 = load double, ptr %v3675, align 8, !tbaa !4
  %v3677 = ptrtoint ptr %a1 to i64
  %v3678 = ptrtoint ptr inttoptr (i64 11 to ptr) to i64
  %v3679 = sub i64 %v3678, 1
  %v3680 = add nsw i64 %v3677, %v3679
  %v3681 = inttoptr i64 %v3680 to ptr
  %v3682 = ptrtoint ptr %v3681 to i64
  %v3683 = ashr i64 %v3682, 1
  %v3684 = and i64 %v3682, 1
  %v3685 = icmp ne i64 %v3684, 0
  %v3686 = icmp ult i64 %v3683, %v3522
  %v3687 = and i1 %v3685, %v3686
  br i1 %v3687, label %array.valid.3688, label %array.invalid.3689
array.invalid.3689:
  call void @mlf_bounds_failure()
  unreachable
array.valid.3688:
  %v3690 = getelementptr i64, ptr %v3524, i64 %v3683
  %v3691 = load double, ptr %v3690, align 8, !tbaa !4
  %v3692 = ptrtoint ptr %a2 to i64
  %v3693 = ptrtoint ptr inttoptr (i64 7 to ptr) to i64
  %v3694 = sub i64 %v3693, 1
  %v3695 = add nsw i64 %v3692, %v3694
  %v3696 = inttoptr i64 %v3695 to ptr
  %v3697 = ptrtoint ptr %v3696 to i64
  %v3698 = ashr i64 %v3697, 1
  %v3699 = and i64 %v3697, 1
  %v3700 = icmp ne i64 %v3699, 0
  %v3701 = icmp ult i64 %v3698, %v3522
  %v3702 = and i1 %v3700, %v3701
  br i1 %v3702, label %array.valid.3703, label %array.invalid.3704
array.invalid.3704:
  call void @mlf_bounds_failure()
  unreachable
array.valid.3703:
  %v3705 = getelementptr i64, ptr %v3524, i64 %v3698
  %v3706 = load double, ptr %v3705, align 8, !tbaa !4
  %v3707 = ptrtoint ptr %a2 to i64
  %v3708 = ptrtoint ptr inttoptr (i64 9 to ptr) to i64
  %v3709 = sub i64 %v3708, 1
  %v3710 = add nsw i64 %v3707, %v3709
  %v3711 = inttoptr i64 %v3710 to ptr
  %v3712 = ptrtoint ptr %v3711 to i64
  %v3713 = ashr i64 %v3712, 1
  %v3714 = and i64 %v3712, 1
  %v3715 = icmp ne i64 %v3714, 0
  %v3716 = icmp ult i64 %v3713, %v3522
  %v3717 = and i1 %v3715, %v3716
  br i1 %v3717, label %array.valid.3718, label %array.invalid.3719
array.invalid.3719:
  call void @mlf_bounds_failure()
  unreachable
array.valid.3718:
  %v3720 = getelementptr i64, ptr %v3524, i64 %v3713
  %v3721 = load double, ptr %v3720, align 8, !tbaa !4
  %v3722 = ptrtoint ptr %a2 to i64
  %v3723 = ptrtoint ptr inttoptr (i64 11 to ptr) to i64
  %v3724 = sub i64 %v3723, 1
  %v3725 = add nsw i64 %v3722, %v3724
  %v3726 = inttoptr i64 %v3725 to ptr
  %v3727 = ptrtoint ptr %v3726 to i64
  %v3728 = ashr i64 %v3727, 1
  %v3729 = and i64 %v3727, 1
  %v3730 = icmp ne i64 %v3729, 0
  %v3731 = icmp ult i64 %v3728, %v3522
  %v3732 = and i1 %v3730, %v3731
  br i1 %v3732, label %array.valid.3733, label %array.invalid.3734
array.invalid.3734:
  call void @mlf_bounds_failure()
  unreachable
array.valid.3733:
  %v3735 = getelementptr i64, ptr %v3524, i64 %v3728
  %v3736 = load double, ptr %v3735, align 8, !tbaa !4
  %v3737 = fmul double %v3635, %v3634
  %v3738 = fmul double %v3737, %v3646
  %v3739 = fsub double %v3661, %v3738
  %v3740 = ptrtoint ptr %a1 to i64
  %v3741 = ptrtoint ptr inttoptr (i64 7 to ptr) to i64
  %v3742 = sub i64 %v3741, 1
  %v3743 = add nsw i64 %v3740, %v3742
  %v3744 = inttoptr i64 %v3743 to ptr
  %v3745 = ptrtoint ptr %v3744 to i64
  %v3746 = ashr i64 %v3745, 1
  %v3747 = and i64 %v3745, 1
  %v3748 = icmp ne i64 %v3747, 0
  %v3749 = icmp ult i64 %v3746, %v3522
  %v3750 = and i1 %v3748, %v3749
  br i1 %v3750, label %array.valid.3751, label %array.invalid.3752
array.invalid.3752:
  call void @mlf_bounds_failure()
  unreachable
array.valid.3751:
  %v3753 = getelementptr i64, ptr %v3524, i64 %v3746
  store double %v3739, ptr %v3753, align 8, !tbaa !4
  %v3754 = fmul double %v3636, %v3634
  %v3755 = fmul double %v3754, %v3646
  %v3756 = fsub double %v3676, %v3755
  %v3757 = ptrtoint ptr %a1 to i64
  %v3758 = ptrtoint ptr inttoptr (i64 9 to ptr) to i64
  %v3759 = sub i64 %v3758, 1
  %v3760 = add nsw i64 %v3757, %v3759
  %v3761 = inttoptr i64 %v3760 to ptr
  %v3762 = ptrtoint ptr %v3761 to i64
  %v3763 = ashr i64 %v3762, 1
  %v3764 = and i64 %v3762, 1
  %v3765 = icmp ne i64 %v3764, 0
  %v3766 = icmp ult i64 %v3763, %v3522
  %v3767 = and i1 %v3765, %v3766
  br i1 %v3767, label %array.valid.3768, label %array.invalid.3769
array.invalid.3769:
  call void @mlf_bounds_failure()
  unreachable
array.valid.3768:
  %v3770 = getelementptr i64, ptr %v3524, i64 %v3763
  store double %v3756, ptr %v3770, align 8, !tbaa !4
  %v3771 = fmul double %v3637, %v3634
  %v3772 = fmul double %v3771, %v3646
  %v3773 = fsub double %v3691, %v3772
  %v3774 = ptrtoint ptr %a1 to i64
  %v3775 = ptrtoint ptr inttoptr (i64 11 to ptr) to i64
  %v3776 = sub i64 %v3775, 1
  %v3777 = add nsw i64 %v3774, %v3776
  %v3778 = inttoptr i64 %v3777 to ptr
  %v3779 = ptrtoint ptr %v3778 to i64
  %v3780 = ashr i64 %v3779, 1
  %v3781 = and i64 %v3779, 1
  %v3782 = icmp ne i64 %v3781, 0
  %v3783 = icmp ult i64 %v3780, %v3522
  %v3784 = and i1 %v3782, %v3783
  br i1 %v3784, label %array.valid.3785, label %array.invalid.3786
array.invalid.3786:
  call void @mlf_bounds_failure()
  unreachable
array.valid.3785:
  %v3787 = getelementptr i64, ptr %v3524, i64 %v3780
  store double %v3773, ptr %v3787, align 8, !tbaa !4
  %v3788 = fmul double %v3635, %v3579
  %v3789 = fmul double %v3788, %v3646
  %v3790 = fadd double %v3706, %v3789
  %v3791 = ptrtoint ptr %a2 to i64
  %v3792 = ptrtoint ptr inttoptr (i64 7 to ptr) to i64
  %v3793 = sub i64 %v3792, 1
  %v3794 = add nsw i64 %v3791, %v3793
  %v3795 = inttoptr i64 %v3794 to ptr
  %v3796 = ptrtoint ptr %v3795 to i64
  %v3797 = ashr i64 %v3796, 1
  %v3798 = and i64 %v3796, 1
  %v3799 = icmp ne i64 %v3798, 0
  %v3800 = icmp ult i64 %v3797, %v3522
  %v3801 = and i1 %v3799, %v3800
  br i1 %v3801, label %array.valid.3802, label %array.invalid.3803
array.invalid.3803:
  call void @mlf_bounds_failure()
  unreachable
array.valid.3802:
  %v3804 = getelementptr i64, ptr %v3524, i64 %v3797
  store double %v3790, ptr %v3804, align 8, !tbaa !4
  %v3805 = fmul double %v3636, %v3579
  %v3806 = fmul double %v3805, %v3646
  %v3807 = fadd double %v3721, %v3806
  %v3808 = ptrtoint ptr %a2 to i64
  %v3809 = ptrtoint ptr inttoptr (i64 9 to ptr) to i64
  %v3810 = sub i64 %v3809, 1
  %v3811 = add nsw i64 %v3808, %v3810
  %v3812 = inttoptr i64 %v3811 to ptr
  %v3813 = ptrtoint ptr %v3812 to i64
  %v3814 = ashr i64 %v3813, 1
  %v3815 = and i64 %v3813, 1
  %v3816 = icmp ne i64 %v3815, 0
  %v3817 = icmp ult i64 %v3814, %v3522
  %v3818 = and i1 %v3816, %v3817
  br i1 %v3818, label %array.valid.3819, label %array.invalid.3820
array.invalid.3820:
  call void @mlf_bounds_failure()
  unreachable
array.valid.3819:
  %v3821 = getelementptr i64, ptr %v3524, i64 %v3814
  store double %v3807, ptr %v3821, align 8, !tbaa !4
  %v3822 = fmul double %v3637, %v3579
  %v3823 = fmul double %v3822, %v3646
  %v3824 = fadd double %v3736, %v3823
  %v3825 = ptrtoint ptr %a2 to i64
  %v3826 = ptrtoint ptr inttoptr (i64 11 to ptr) to i64
  %v3827 = sub i64 %v3826, 1
  %v3828 = add nsw i64 %v3825, %v3827
  %v3829 = inttoptr i64 %v3828 to ptr
  %v3830 = ptrtoint ptr %v3829 to i64
  %v3831 = ashr i64 %v3830, 1
  %v3832 = and i64 %v3830, 1
  %v3833 = icmp ne i64 %v3832, 0
  %v3834 = icmp ult i64 %v3831, %v3522
  %v3835 = and i1 %v3833, %v3834
  br i1 %v3835, label %array.valid.3836, label %array.invalid.3837
array.invalid.3837:
  call void @mlf_bounds_failure()
  unreachable
array.valid.3836:
  %v3838 = getelementptr i64, ptr %v3524, i64 %v3831
  store double %v3824, ptr %v3838, align 8, !tbaa !4
  %v3839 = ptrtoint ptr %a2 to i64
  %v3840 = ptrtoint ptr inttoptr (i64 15 to ptr) to i64
  %v3841 = sub i64 %v3840, 1
  %v3842 = add nsw i64 %v3839, %v3841
  %v3843 = inttoptr i64 %v3842 to ptr
  %v3844 = musttail call ptr @mlf.numeric.42(ptr %a0, ptr %a1, ptr %v3843)
  ret ptr %v3844
}

define private ptr @mlf.numeric.77(ptr %a0, ptr %a1) alwaysinline {
entry:
  %v3471 = ptrtoint ptr %a1 to i64
  %v3472 = ptrtoint ptr inttoptr (i64 71 to ptr) to i64
  %v3473 = and i64 %v3471, %v3472
  %v3474 = and i64 %v3473, 1
  %v3475 = icmp ne i64 %v3474, 0
  br i1 %v3475, label %yes.3476, label %no.3477
yes.3476:
  %v3479 = icmp eq i64 %v3471, %v3472
  %v3480 = select i1 %v3479, ptr inttoptr (i64 6 to ptr), ptr inttoptr (i64 2 to ptr)
  br label %join.3478
no.3477:
  %v3481 = call ptr @mlf_eq_int(ptr %a1, ptr inttoptr (i64 71 to ptr))
  br label %join.3478
join.3478:
  %v3482 = phi ptr [ %v3480, %yes.3476 ], [ %v3481, %no.3477 ]
  %v3483 = icmp eq ptr %v3482, inttoptr (i64 6 to ptr)
  br i1 %v3483, label %tail.yes.3484, label %tail.no.3485
tail.yes.3484:
  ret ptr inttoptr (i64 4 to ptr)
tail.no.3485:
  %v3486 = ptrtoint ptr %a1 to i64
  %v3487 = ptrtoint ptr inttoptr (i64 15 to ptr) to i64
  %v3488 = and i64 %v3486, %v3487
  %v3489 = and i64 %v3488, 1
  %v3490 = icmp ne i64 %v3489, 0
  br i1 %v3490, label %yes.3491, label %no.3492
yes.3491:
  %v3494 = sub i64 %v3487, 1
  %v3495 = call { i64, i1 } @llvm.sadd.with.overflow.i64(i64 %v3486, i64 %v3494)
  %v3496 = extractvalue { i64, i1 } %v3495, 0
  %v3497 = extractvalue { i64, i1 } %v3495, 1
  br i1 %v3497, label %yes.3498, label %no.3499
yes.3498:
  %v3501 = call ptr @mlf_add_int(ptr %a1, ptr inttoptr (i64 15 to ptr))
  br label %join.3500
no.3499:
  %v3502 = inttoptr i64 %v3496 to ptr
  br label %join.3500
join.3500:
  %v3503 = phi ptr [ %v3501, %yes.3498 ], [ %v3502, %no.3499 ]
  br label %join.3493
no.3492:
  %v3504 = call ptr @mlf_add_int(ptr %a1, ptr inttoptr (i64 15 to ptr))
  br label %join.3493
join.3493:
  %v3505 = phi ptr [ %v3503, %join.3500 ], [ %v3504, %no.3492 ]
  %v3845 = call ptr @mlf.numeric.42(ptr %a0, ptr %a1, ptr %v3505)
  %v3846 = ptrtoint ptr %a1 to i64
  %v3847 = ptrtoint ptr inttoptr (i64 15 to ptr) to i64
  %v3848 = and i64 %v3846, %v3847
  %v3849 = and i64 %v3848, 1
  %v3850 = icmp ne i64 %v3849, 0
  br i1 %v3850, label %yes.3851, label %no.3852
yes.3851:
  %v3854 = sub i64 %v3847, 1
  %v3855 = call { i64, i1 } @llvm.sadd.with.overflow.i64(i64 %v3846, i64 %v3854)
  %v3856 = extractvalue { i64, i1 } %v3855, 0
  %v3857 = extractvalue { i64, i1 } %v3855, 1
  br i1 %v3857, label %yes.3858, label %no.3859
yes.3858:
  %v3861 = call ptr @mlf_add_int(ptr %a1, ptr inttoptr (i64 15 to ptr))
  br label %join.3860
no.3859:
  %v3862 = inttoptr i64 %v3856 to ptr
  br label %join.3860
join.3860:
  %v3863 = phi ptr [ %v3861, %yes.3858 ], [ %v3862, %no.3859 ]
  br label %join.3853
no.3852:
  %v3864 = call ptr @mlf_add_int(ptr %a1, ptr inttoptr (i64 15 to ptr))
  br label %join.3853
join.3853:
  %v3865 = phi ptr [ %v3863, %join.3860 ], [ %v3864, %no.3852 ]
  %v3866 = musttail call ptr @mlf.numeric.77(ptr %a0, ptr %v3865)
  ret ptr %v3866
}

define private ptr @mlf.numeric.81(ptr %a0, ptr %a1) alwaysinline {
entry:
  %v3868 = ptrtoint ptr %a1 to i64
  %v3869 = ptrtoint ptr inttoptr (i64 71 to ptr) to i64
  %v3870 = and i64 %v3868, %v3869
  %v3871 = and i64 %v3870, 1
  %v3872 = icmp ne i64 %v3871, 0
  br i1 %v3872, label %yes.3873, label %no.3874
yes.3873:
  %v3876 = icmp eq i64 %v3868, %v3869
  %v3877 = select i1 %v3876, ptr inttoptr (i64 6 to ptr), ptr inttoptr (i64 2 to ptr)
  br label %join.3875
no.3874:
  %v3878 = call ptr @mlf_eq_int(ptr %a1, ptr inttoptr (i64 71 to ptr))
  br label %join.3875
join.3875:
  %v3879 = phi ptr [ %v3877, %yes.3873 ], [ %v3878, %no.3874 ]
  %v3880 = icmp eq ptr %v3879, inttoptr (i64 6 to ptr)
  br i1 %v3880, label %tail.yes.3881, label %tail.no.3882
tail.yes.3881:
  ret ptr inttoptr (i64 4 to ptr)
tail.no.3882:
  %v3883 = getelementptr i8, ptr %a0, i64 24
  %v3884 = load i64, ptr %v3883, align 8, !tbaa !3
  %v3885 = getelementptr i8, ptr %a0, i64 32
  %v3886 = load ptr, ptr %v3885, align 8, !tbaa !3
  %v3887 = ptrtoint ptr %a1 to i64
  %v3888 = ashr i64 %v3887, 1
  %v3889 = and i64 %v3887, 1
  %v3890 = icmp ne i64 %v3889, 0
  %v3891 = icmp ult i64 %v3888, %v3884
  %v3892 = and i1 %v3890, %v3891
  br i1 %v3892, label %array.valid.3893, label %array.invalid.3894
array.invalid.3894:
  call void @mlf_bounds_failure()
  unreachable
array.valid.3893:
  %v3895 = getelementptr i64, ptr %v3886, i64 %v3888
  %v3896 = load double, ptr %v3895, align 8, !tbaa !4
  %v3897 = ptrtoint ptr %a1 to i64
  %v3898 = ptrtoint ptr inttoptr (i64 3 to ptr) to i64
  %v3899 = sub i64 %v3898, 1
  %v3900 = add nsw i64 %v3897, %v3899
  %v3901 = inttoptr i64 %v3900 to ptr
  %v3902 = ptrtoint ptr %v3901 to i64
  %v3903 = ashr i64 %v3902, 1
  %v3904 = and i64 %v3902, 1
  %v3905 = icmp ne i64 %v3904, 0
  %v3906 = icmp ult i64 %v3903, %v3884
  %v3907 = and i1 %v3905, %v3906
  br i1 %v3907, label %array.valid.3908, label %array.invalid.3909
array.invalid.3909:
  call void @mlf_bounds_failure()
  unreachable
array.valid.3908:
  %v3910 = getelementptr i64, ptr %v3886, i64 %v3903
  %v3911 = load double, ptr %v3910, align 8, !tbaa !4
  %v3912 = ptrtoint ptr %a1 to i64
  %v3913 = ptrtoint ptr inttoptr (i64 5 to ptr) to i64
  %v3914 = sub i64 %v3913, 1
  %v3915 = add nsw i64 %v3912, %v3914
  %v3916 = inttoptr i64 %v3915 to ptr
  %v3917 = ptrtoint ptr %v3916 to i64
  %v3918 = ashr i64 %v3917, 1
  %v3919 = and i64 %v3917, 1
  %v3920 = icmp ne i64 %v3919, 0
  %v3921 = icmp ult i64 %v3918, %v3884
  %v3922 = and i1 %v3920, %v3921
  br i1 %v3922, label %array.valid.3923, label %array.invalid.3924
array.invalid.3924:
  call void @mlf_bounds_failure()
  unreachable
array.valid.3923:
  %v3925 = getelementptr i64, ptr %v3886, i64 %v3918
  %v3926 = load double, ptr %v3925, align 8, !tbaa !4
  %v3927 = ptrtoint ptr %a1 to i64
  %v3928 = ptrtoint ptr inttoptr (i64 7 to ptr) to i64
  %v3929 = sub i64 %v3928, 1
  %v3930 = add nsw i64 %v3927, %v3929
  %v3931 = inttoptr i64 %v3930 to ptr
  %v3932 = ptrtoint ptr %v3931 to i64
  %v3933 = ashr i64 %v3932, 1
  %v3934 = and i64 %v3932, 1
  %v3935 = icmp ne i64 %v3934, 0
  %v3936 = icmp ult i64 %v3933, %v3884
  %v3937 = and i1 %v3935, %v3936
  br i1 %v3937, label %array.valid.3938, label %array.invalid.3939
array.invalid.3939:
  call void @mlf_bounds_failure()
  unreachable
array.valid.3938:
  %v3940 = getelementptr i64, ptr %v3886, i64 %v3933
  %v3941 = load double, ptr %v3940, align 8, !tbaa !4
  %v3942 = ptrtoint ptr %a1 to i64
  %v3943 = ptrtoint ptr inttoptr (i64 9 to ptr) to i64
  %v3944 = sub i64 %v3943, 1
  %v3945 = add nsw i64 %v3942, %v3944
  %v3946 = inttoptr i64 %v3945 to ptr
  %v3947 = ptrtoint ptr %v3946 to i64
  %v3948 = ashr i64 %v3947, 1
  %v3949 = and i64 %v3947, 1
  %v3950 = icmp ne i64 %v3949, 0
  %v3951 = icmp ult i64 %v3948, %v3884
  %v3952 = and i1 %v3950, %v3951
  br i1 %v3952, label %array.valid.3953, label %array.invalid.3954
array.invalid.3954:
  call void @mlf_bounds_failure()
  unreachable
array.valid.3953:
  %v3955 = getelementptr i64, ptr %v3886, i64 %v3948
  %v3956 = load double, ptr %v3955, align 8, !tbaa !4
  %v3957 = ptrtoint ptr %a1 to i64
  %v3958 = ptrtoint ptr inttoptr (i64 11 to ptr) to i64
  %v3959 = sub i64 %v3958, 1
  %v3960 = add nsw i64 %v3957, %v3959
  %v3961 = inttoptr i64 %v3960 to ptr
  %v3962 = ptrtoint ptr %v3961 to i64
  %v3963 = ashr i64 %v3962, 1
  %v3964 = and i64 %v3962, 1
  %v3965 = icmp ne i64 %v3964, 0
  %v3966 = icmp ult i64 %v3963, %v3884
  %v3967 = and i1 %v3965, %v3966
  br i1 %v3967, label %array.valid.3968, label %array.invalid.3969
array.invalid.3969:
  call void @mlf_bounds_failure()
  unreachable
array.valid.3968:
  %v3970 = getelementptr i64, ptr %v3886, i64 %v3963
  %v3971 = load double, ptr %v3970, align 8, !tbaa !4
  %v3972 = fmul double 0x3f847ae147ae147b, %v3941
  %v3973 = fadd double %v3896, %v3972
  %v3974 = ptrtoint ptr %a1 to i64
  %v3975 = ashr i64 %v3974, 1
  %v3976 = and i64 %v3974, 1
  %v3977 = icmp ne i64 %v3976, 0
  %v3978 = icmp ult i64 %v3975, %v3884
  %v3979 = and i1 %v3977, %v3978
  br i1 %v3979, label %array.valid.3980, label %array.invalid.3981
array.invalid.3981:
  call void @mlf_bounds_failure()
  unreachable
array.valid.3980:
  %v3982 = getelementptr i64, ptr %v3886, i64 %v3975
  store double %v3973, ptr %v3982, align 8, !tbaa !4
  %v3983 = fmul double 0x3f847ae147ae147b, %v3956
  %v3984 = fadd double %v3911, %v3983
  %v3985 = ptrtoint ptr %a1 to i64
  %v3986 = ptrtoint ptr inttoptr (i64 3 to ptr) to i64
  %v3987 = sub i64 %v3986, 1
  %v3988 = add nsw i64 %v3985, %v3987
  %v3989 = inttoptr i64 %v3988 to ptr
  %v3990 = ptrtoint ptr %v3989 to i64
  %v3991 = ashr i64 %v3990, 1
  %v3992 = and i64 %v3990, 1
  %v3993 = icmp ne i64 %v3992, 0
  %v3994 = icmp ult i64 %v3991, %v3884
  %v3995 = and i1 %v3993, %v3994
  br i1 %v3995, label %array.valid.3996, label %array.invalid.3997
array.invalid.3997:
  call void @mlf_bounds_failure()
  unreachable
array.valid.3996:
  %v3998 = getelementptr i64, ptr %v3886, i64 %v3991
  store double %v3984, ptr %v3998, align 8, !tbaa !4
  %v3999 = fmul double 0x3f847ae147ae147b, %v3971
  %v4000 = fadd double %v3926, %v3999
  %v4001 = ptrtoint ptr %a1 to i64
  %v4002 = ptrtoint ptr inttoptr (i64 5 to ptr) to i64
  %v4003 = sub i64 %v4002, 1
  %v4004 = add nsw i64 %v4001, %v4003
  %v4005 = inttoptr i64 %v4004 to ptr
  %v4006 = ptrtoint ptr %v4005 to i64
  %v4007 = ashr i64 %v4006, 1
  %v4008 = and i64 %v4006, 1
  %v4009 = icmp ne i64 %v4008, 0
  %v4010 = icmp ult i64 %v4007, %v3884
  %v4011 = and i1 %v4009, %v4010
  br i1 %v4011, label %array.valid.4012, label %array.invalid.4013
array.invalid.4013:
  call void @mlf_bounds_failure()
  unreachable
array.valid.4012:
  %v4014 = getelementptr i64, ptr %v3886, i64 %v4007
  store double %v4000, ptr %v4014, align 8, !tbaa !4
  %v4015 = ptrtoint ptr %a1 to i64
  %v4016 = ptrtoint ptr inttoptr (i64 15 to ptr) to i64
  %v4017 = sub i64 %v4016, 1
  %v4018 = add nsw i64 %v4015, %v4017
  %v4019 = inttoptr i64 %v4018 to ptr
  %v4020 = musttail call ptr @mlf.numeric.81(ptr %a0, ptr %v4019)
  ret ptr %v4020
}

define private ptr @mlf.numeric.96(ptr %a0, ptr %a1) alwaysinline {
entry:
  %v3456 = ptrtoint ptr %a1 to i64
  %v3457 = ptrtoint ptr inttoptr (i64 1 to ptr) to i64
  %v3458 = and i64 %v3456, %v3457
  %v3459 = and i64 %v3458, 1
  %v3460 = icmp ne i64 %v3459, 0
  br i1 %v3460, label %yes.3461, label %no.3462
yes.3461:
  %v3464 = icmp eq i64 %v3456, %v3457
  %v3465 = select i1 %v3464, ptr inttoptr (i64 6 to ptr), ptr inttoptr (i64 2 to ptr)
  br label %join.3463
no.3462:
  %v3466 = call ptr @mlf_eq_int(ptr %a1, ptr inttoptr (i64 1 to ptr))
  br label %join.3463
join.3463:
  %v3467 = phi ptr [ %v3465, %yes.3461 ], [ %v3466, %no.3462 ]
  %v3468 = icmp eq ptr %v3467, inttoptr (i64 6 to ptr)
  br i1 %v3468, label %tail.yes.3469, label %tail.no.3470
tail.yes.3469:
  ret ptr inttoptr (i64 4 to ptr)
tail.no.3470:
  %v3867 = call ptr @mlf.numeric.77(ptr %a0, ptr inttoptr (i64 1 to ptr))
  %v4021 = call ptr @mlf.numeric.81(ptr %a0, ptr inttoptr (i64 1 to ptr))
  %v4022 = ptrtoint ptr %a1 to i64
  %v4023 = ptrtoint ptr inttoptr (i64 3 to ptr) to i64
  %v4024 = and i64 %v4022, %v4023
  %v4025 = and i64 %v4024, 1
  %v4026 = icmp ne i64 %v4025, 0
  br i1 %v4026, label %yes.4027, label %no.4028
yes.4027:
  %v4030 = sub i64 %v4023, 1
  %v4031 = call { i64, i1 } @llvm.ssub.with.overflow.i64(i64 %v4022, i64 %v4030)
  %v4032 = extractvalue { i64, i1 } %v4031, 0
  %v4033 = extractvalue { i64, i1 } %v4031, 1
  br i1 %v4033, label %yes.4034, label %no.4035
yes.4034:
  %v4037 = call ptr @mlf_sub_int(ptr %a1, ptr inttoptr (i64 3 to ptr))
  br label %join.4036
no.4035:
  %v4038 = inttoptr i64 %v4032 to ptr
  br label %join.4036
join.4036:
  %v4039 = phi ptr [ %v4037, %yes.4034 ], [ %v4038, %no.4035 ]
  br label %join.4029
no.4028:
  %v4040 = call ptr @mlf_sub_int(ptr %a1, ptr inttoptr (i64 3 to ptr))
  br label %join.4029
join.4029:
  %v4041 = phi ptr [ %v4039, %join.4036 ], [ %v4040, %no.4028 ]
  %v4042 = musttail call ptr @mlf.numeric.96(ptr %a0, ptr %v4041)
  ret ptr %v4042
}

define private ptr @mlf.code.4113(ptr %env, ptr %arg) {
entry:
  %v4114 = getelementptr i8, ptr %env, i64 24
  %v4115 = load ptr, ptr %v4114, align 8, !tbaa !3
  %v4116 = call ptr @mlf_force(ptr %v4115)
  %v4117 = call ptr @mlf_prim2(i64 8, ptr %v4116, ptr inttoptr (i64 1 to ptr))
  ret ptr %v4117
}

define private ptr @mlf.code.4108(ptr %env, ptr %arg) {
entry:
  %v4109 = getelementptr i8, ptr %env, i64 24
  %v4110 = load ptr, ptr %v4109, align 8, !tbaa !3
  %v4111 = getelementptr i8, ptr %env, i64 32
  %v4112 = load ptr, ptr %v4111, align 8, !tbaa !3
  %v4118 = call ptr @mlf_env_new(i64 1)
  %v4119 = getelementptr i8, ptr %v4118, i64 24
  store ptr %v4112, ptr %v4119, align 8, !tbaa !3
  %v4120 = call ptr @mlf_thunk(ptr @mlf.code.4113, ptr %v4118)
  %v4121 = call ptr @mlf_prim2(i64 32, ptr %v4110, ptr %v4120)
  ret ptr %v4121
}

define private ptr @mlf.code.4138(ptr %env, ptr %arg) {
entry:
  %v4139 = getelementptr i8, ptr %env, i64 24
  %v4140 = load ptr, ptr %v4139, align 8, !tbaa !3
  %v4141 = call ptr @mlf_force(ptr %v4140)
  %v4142 = call ptr @mlf_prim2(i64 8, ptr %v4141, ptr inttoptr (i64 3 to ptr))
  ret ptr %v4142
}

define private ptr @mlf.code.4133(ptr %env, ptr %arg) {
entry:
  %v4134 = getelementptr i8, ptr %env, i64 24
  %v4135 = load ptr, ptr %v4134, align 8, !tbaa !3
  %v4136 = getelementptr i8, ptr %env, i64 32
  %v4137 = load ptr, ptr %v4136, align 8, !tbaa !3
  %v4143 = call ptr @mlf_env_new(i64 1)
  %v4144 = getelementptr i8, ptr %v4143, i64 24
  store ptr %v4137, ptr %v4144, align 8, !tbaa !3
  %v4145 = call ptr @mlf_thunk(ptr @mlf.code.4138, ptr %v4143)
  %v4146 = call ptr @mlf_prim2(i64 32, ptr %v4135, ptr %v4145)
  ret ptr %v4146
}

define private ptr @mlf.code.4165(ptr %env, ptr %arg) {
entry:
  %v4166 = getelementptr i8, ptr %env, i64 24
  %v4167 = load ptr, ptr %v4166, align 8, !tbaa !3
  %v4168 = call ptr @mlf_force(ptr %v4167)
  %v4169 = call ptr @mlf_prim2(i64 8, ptr %v4168, ptr inttoptr (i64 5 to ptr))
  ret ptr %v4169
}

define private ptr @mlf.code.4160(ptr %env, ptr %arg) {
entry:
  %v4161 = getelementptr i8, ptr %env, i64 24
  %v4162 = load ptr, ptr %v4161, align 8, !tbaa !3
  %v4163 = getelementptr i8, ptr %env, i64 32
  %v4164 = load ptr, ptr %v4163, align 8, !tbaa !3
  %v4170 = call ptr @mlf_env_new(i64 1)
  %v4171 = getelementptr i8, ptr %v4170, i64 24
  store ptr %v4164, ptr %v4171, align 8, !tbaa !3
  %v4172 = call ptr @mlf_thunk(ptr @mlf.code.4165, ptr %v4170)
  %v4173 = call ptr @mlf_prim2(i64 32, ptr %v4162, ptr %v4172)
  ret ptr %v4173
}

define private ptr @mlf.code.4194(ptr %env, ptr %arg) {
entry:
  %v4195 = getelementptr i8, ptr %env, i64 24
  %v4196 = load ptr, ptr %v4195, align 8, !tbaa !3
  %v4197 = call ptr @mlf_force(ptr %v4196)
  %v4198 = call ptr @mlf_prim2(i64 8, ptr %v4197, ptr inttoptr (i64 13 to ptr))
  ret ptr %v4198
}

define private ptr @mlf.code.4189(ptr %env, ptr %arg) {
entry:
  %v4190 = getelementptr i8, ptr %env, i64 24
  %v4191 = load ptr, ptr %v4190, align 8, !tbaa !3
  %v4192 = getelementptr i8, ptr %env, i64 32
  %v4193 = load ptr, ptr %v4192, align 8, !tbaa !3
  %v4199 = call ptr @mlf_env_new(i64 1)
  %v4200 = getelementptr i8, ptr %v4199, i64 24
  store ptr %v4193, ptr %v4200, align 8, !tbaa !3
  %v4201 = call ptr @mlf_thunk(ptr @mlf.code.4194, ptr %v4199)
  %v4202 = call ptr @mlf_prim2(i64 32, ptr %v4191, ptr %v4201)
  ret ptr %v4202
}

define private ptr @mlf.code.4225(ptr %env, ptr %arg) {
entry:
  %v4226 = getelementptr i8, ptr %env, i64 24
  %v4227 = load ptr, ptr %v4226, align 8, !tbaa !3
  %v4228 = call ptr @mlf_force(ptr %v4227)
  %v4229 = call ptr @mlf_prim2(i64 8, ptr %v4228, ptr inttoptr (i64 1 to ptr))
  ret ptr %v4229
}

define private ptr @mlf.code.4220(ptr %env, ptr %arg) {
entry:
  %v4221 = getelementptr i8, ptr %env, i64 24
  %v4222 = load ptr, ptr %v4221, align 8, !tbaa !3
  %v4223 = getelementptr i8, ptr %env, i64 32
  %v4224 = load ptr, ptr %v4223, align 8, !tbaa !3
  %v4230 = call ptr @mlf_env_new(i64 1)
  %v4231 = getelementptr i8, ptr %v4230, i64 24
  store ptr %v4224, ptr %v4231, align 8, !tbaa !3
  %v4232 = call ptr @mlf_thunk(ptr @mlf.code.4225, ptr %v4230)
  %v4233 = call ptr @mlf_prim2(i64 32, ptr %v4222, ptr %v4232)
  ret ptr %v4233
}

define private ptr @mlf.code.4258(ptr %env, ptr %arg) {
entry:
  %v4259 = getelementptr i8, ptr %env, i64 24
  %v4260 = load ptr, ptr %v4259, align 8, !tbaa !3
  %v4261 = call ptr @mlf_force(ptr %v4260)
  %v4262 = call ptr @mlf_prim2(i64 8, ptr %v4261, ptr inttoptr (i64 3 to ptr))
  ret ptr %v4262
}

define private ptr @mlf.code.4253(ptr %env, ptr %arg) {
entry:
  %v4254 = getelementptr i8, ptr %env, i64 24
  %v4255 = load ptr, ptr %v4254, align 8, !tbaa !3
  %v4256 = getelementptr i8, ptr %env, i64 32
  %v4257 = load ptr, ptr %v4256, align 8, !tbaa !3
  %v4263 = call ptr @mlf_env_new(i64 1)
  %v4264 = getelementptr i8, ptr %v4263, i64 24
  store ptr %v4257, ptr %v4264, align 8, !tbaa !3
  %v4265 = call ptr @mlf_thunk(ptr @mlf.code.4258, ptr %v4263)
  %v4266 = call ptr @mlf_prim2(i64 32, ptr %v4255, ptr %v4265)
  ret ptr %v4266
}

define private ptr @mlf.code.4293(ptr %env, ptr %arg) {
entry:
  %v4294 = getelementptr i8, ptr %env, i64 24
  %v4295 = load ptr, ptr %v4294, align 8, !tbaa !3
  %v4296 = call ptr @mlf_force(ptr %v4295)
  %v4297 = call ptr @mlf_prim2(i64 8, ptr %v4296, ptr inttoptr (i64 5 to ptr))
  ret ptr %v4297
}

define private ptr @mlf.code.4288(ptr %env, ptr %arg) {
entry:
  %v4289 = getelementptr i8, ptr %env, i64 24
  %v4290 = load ptr, ptr %v4289, align 8, !tbaa !3
  %v4291 = getelementptr i8, ptr %env, i64 32
  %v4292 = load ptr, ptr %v4291, align 8, !tbaa !3
  %v4298 = call ptr @mlf_env_new(i64 1)
  %v4299 = getelementptr i8, ptr %v4298, i64 24
  store ptr %v4292, ptr %v4299, align 8, !tbaa !3
  %v4300 = call ptr @mlf_thunk(ptr @mlf.code.4293, ptr %v4298)
  %v4301 = call ptr @mlf_prim2(i64 32, ptr %v4290, ptr %v4300)
  ret ptr %v4301
}

define private ptr @mlf.code.4330(ptr %env, ptr %arg) {
entry:
  %v4331 = getelementptr i8, ptr %env, i64 24
  %v4332 = load ptr, ptr %v4331, align 8, !tbaa !3
  %v4333 = call ptr @mlf_force(ptr %v4332)
  %v4334 = call ptr @mlf_prim2(i64 8, ptr %v4333, ptr inttoptr (i64 13 to ptr))
  ret ptr %v4334
}

define private ptr @mlf.code.4325(ptr %env, ptr %arg) {
entry:
  %v4326 = getelementptr i8, ptr %env, i64 24
  %v4327 = load ptr, ptr %v4326, align 8, !tbaa !3
  %v4328 = getelementptr i8, ptr %env, i64 32
  %v4329 = load ptr, ptr %v4328, align 8, !tbaa !3
  %v4335 = call ptr @mlf_env_new(i64 1)
  %v4336 = getelementptr i8, ptr %v4335, i64 24
  store ptr %v4329, ptr %v4336, align 8, !tbaa !3
  %v4337 = call ptr @mlf_thunk(ptr @mlf.code.4330, ptr %v4335)
  %v4338 = call ptr @mlf_prim2(i64 32, ptr %v4327, ptr %v4337)
  ret ptr %v4338
}

define private ptr @mlf.code.4364(ptr %env, ptr %arg) {
entry:
  %v4365 = getelementptr i8, ptr %env, i64 24
  %v4366 = load ptr, ptr %v4365, align 8, !tbaa !3
  %v4367 = getelementptr i8, ptr %env, i64 32
  %v4368 = load ptr, ptr %v4367, align 8, !tbaa !3
  %v4369 = call ptr @mlf_force(ptr %v4366)
  %v4370 = call ptr @mlf_force(ptr %v4368)
  %v4371 = call ptr @mlf_prim2(i64 19, ptr %v4369, ptr %v4370)
  ret ptr %v4371
}

define private ptr @mlf.code.4376(ptr %env, ptr %arg) {
entry:
  %v4377 = getelementptr i8, ptr %env, i64 24
  %v4378 = load ptr, ptr %v4377, align 8, !tbaa !3
  %v4379 = getelementptr i8, ptr %env, i64 32
  %v4380 = load ptr, ptr %v4379, align 8, !tbaa !3
  %v4381 = call ptr @mlf_force(ptr %v4378)
  %v4382 = call ptr @mlf_force(ptr %v4380)
  %v4383 = call ptr @mlf_prim2(i64 19, ptr %v4381, ptr %v4382)
  ret ptr %v4383
}

define private ptr @mlf.code.4388(ptr %env, ptr %arg) {
entry:
  %v4389 = getelementptr i8, ptr %env, i64 24
  %v4390 = load ptr, ptr %v4389, align 8, !tbaa !3
  %v4391 = getelementptr i8, ptr %env, i64 32
  %v4392 = load ptr, ptr %v4391, align 8, !tbaa !3
  %v4393 = call ptr @mlf_force(ptr %v4390)
  %v4394 = call ptr @mlf_force(ptr %v4392)
  %v4395 = call ptr @mlf_prim2(i64 19, ptr %v4393, ptr %v4394)
  ret ptr %v4395
}

define private ptr @mlf.code.4400(ptr %env, ptr %arg) {
entry:
  %v4401 = getelementptr i8, ptr %env, i64 24
  %v4402 = load ptr, ptr %v4401, align 8, !tbaa !3
  %v4403 = getelementptr i8, ptr %env, i64 32
  %v4404 = load ptr, ptr %v4403, align 8, !tbaa !3
  %v4405 = getelementptr i8, ptr %env, i64 40
  %v4406 = load ptr, ptr %v4405, align 8, !tbaa !3
  %v4407 = call ptr @mlf_force(ptr %v4402)
  %v4408 = call ptr @mlf_prim2(i64 20, ptr %v4407, ptr %v4407)
  %v4409 = call ptr @mlf_force(ptr %v4404)
  %v4410 = call ptr @mlf_prim2(i64 20, ptr %v4409, ptr %v4409)
  %v4411 = call ptr @mlf_prim2(i64 18, ptr %v4408, ptr %v4410)
  %v4412 = call ptr @mlf_force(ptr %v4406)
  %v4413 = call ptr @mlf_prim2(i64 20, ptr %v4412, ptr %v4412)
  %v4414 = call ptr @mlf_prim2(i64 18, ptr %v4411, ptr %v4413)
  %v4415 = call ptr @mlf_prim1(i64 22, ptr %v4414)
  ret ptr %v4415
}

define private ptr @mlf.code.4421(ptr %env, ptr %arg) {
entry:
  %v4422 = getelementptr i8, ptr %env, i64 24
  %v4423 = load ptr, ptr %v4422, align 8, !tbaa !3
  %v4424 = call ptr @mlf_double(double 0x3f847ae147ae147b)
  %v4425 = call ptr @mlf_force(ptr %v4423)
  %v4426 = call ptr @mlf_prim2(i64 20, ptr %v4425, ptr %v4425)
  %v4427 = call ptr @mlf_prim2(i64 20, ptr %v4426, ptr %v4425)
  %v4428 = call ptr @mlf_prim2(i64 21, ptr %v4424, ptr %v4427)
  ret ptr %v4428
}

define private ptr @mlf.code.4437(ptr %env, ptr %arg) {
entry:
  %v4438 = getelementptr i8, ptr %env, i64 24
  %v4439 = load ptr, ptr %v4438, align 8, !tbaa !3
  %v4440 = call ptr @mlf_force(ptr %v4439)
  %v4441 = call ptr @mlf_prim2(i64 8, ptr %v4440, ptr inttoptr (i64 7 to ptr))
  ret ptr %v4441
}

define private ptr @mlf.code.4432(ptr %env, ptr %arg) {
entry:
  %v4433 = getelementptr i8, ptr %env, i64 24
  %v4434 = load ptr, ptr %v4433, align 8, !tbaa !3
  %v4435 = getelementptr i8, ptr %env, i64 32
  %v4436 = load ptr, ptr %v4435, align 8, !tbaa !3
  %v4442 = call ptr @mlf_env_new(i64 1)
  %v4443 = getelementptr i8, ptr %v4442, i64 24
  store ptr %v4436, ptr %v4443, align 8, !tbaa !3
  %v4444 = call ptr @mlf_thunk(ptr @mlf.code.4437, ptr %v4442)
  %v4445 = call ptr @mlf_prim2(i64 32, ptr %v4434, ptr %v4444)
  ret ptr %v4445
}

define private ptr @mlf.code.4474(ptr %env, ptr %arg) {
entry:
  %v4475 = getelementptr i8, ptr %env, i64 24
  %v4476 = load ptr, ptr %v4475, align 8, !tbaa !3
  %v4477 = call ptr @mlf_force(ptr %v4476)
  %v4478 = call ptr @mlf_prim2(i64 8, ptr %v4477, ptr inttoptr (i64 9 to ptr))
  ret ptr %v4478
}

define private ptr @mlf.code.4469(ptr %env, ptr %arg) {
entry:
  %v4470 = getelementptr i8, ptr %env, i64 24
  %v4471 = load ptr, ptr %v4470, align 8, !tbaa !3
  %v4472 = getelementptr i8, ptr %env, i64 32
  %v4473 = load ptr, ptr %v4472, align 8, !tbaa !3
  %v4479 = call ptr @mlf_env_new(i64 1)
  %v4480 = getelementptr i8, ptr %v4479, i64 24
  store ptr %v4473, ptr %v4480, align 8, !tbaa !3
  %v4481 = call ptr @mlf_thunk(ptr @mlf.code.4474, ptr %v4479)
  %v4482 = call ptr @mlf_prim2(i64 32, ptr %v4471, ptr %v4481)
  ret ptr %v4482
}

define private ptr @mlf.code.4513(ptr %env, ptr %arg) {
entry:
  %v4514 = getelementptr i8, ptr %env, i64 24
  %v4515 = load ptr, ptr %v4514, align 8, !tbaa !3
  %v4516 = call ptr @mlf_force(ptr %v4515)
  %v4517 = call ptr @mlf_prim2(i64 8, ptr %v4516, ptr inttoptr (i64 11 to ptr))
  ret ptr %v4517
}

define private ptr @mlf.code.4508(ptr %env, ptr %arg) {
entry:
  %v4509 = getelementptr i8, ptr %env, i64 24
  %v4510 = load ptr, ptr %v4509, align 8, !tbaa !3
  %v4511 = getelementptr i8, ptr %env, i64 32
  %v4512 = load ptr, ptr %v4511, align 8, !tbaa !3
  %v4518 = call ptr @mlf_env_new(i64 1)
  %v4519 = getelementptr i8, ptr %v4518, i64 24
  store ptr %v4512, ptr %v4519, align 8, !tbaa !3
  %v4520 = call ptr @mlf_thunk(ptr @mlf.code.4513, ptr %v4518)
  %v4521 = call ptr @mlf_prim2(i64 32, ptr %v4510, ptr %v4520)
  ret ptr %v4521
}

define private ptr @mlf.code.4554(ptr %env, ptr %arg) {
entry:
  %v4555 = getelementptr i8, ptr %env, i64 24
  %v4556 = load ptr, ptr %v4555, align 8, !tbaa !3
  %v4557 = call ptr @mlf_force(ptr %v4556)
  %v4558 = call ptr @mlf_prim2(i64 8, ptr %v4557, ptr inttoptr (i64 7 to ptr))
  ret ptr %v4558
}

define private ptr @mlf.code.4549(ptr %env, ptr %arg) {
entry:
  %v4550 = getelementptr i8, ptr %env, i64 24
  %v4551 = load ptr, ptr %v4550, align 8, !tbaa !3
  %v4552 = getelementptr i8, ptr %env, i64 32
  %v4553 = load ptr, ptr %v4552, align 8, !tbaa !3
  %v4559 = call ptr @mlf_env_new(i64 1)
  %v4560 = getelementptr i8, ptr %v4559, i64 24
  store ptr %v4553, ptr %v4560, align 8, !tbaa !3
  %v4561 = call ptr @mlf_thunk(ptr @mlf.code.4554, ptr %v4559)
  %v4562 = call ptr @mlf_prim2(i64 32, ptr %v4551, ptr %v4561)
  ret ptr %v4562
}

define private ptr @mlf.code.4597(ptr %env, ptr %arg) {
entry:
  %v4598 = getelementptr i8, ptr %env, i64 24
  %v4599 = load ptr, ptr %v4598, align 8, !tbaa !3
  %v4600 = call ptr @mlf_force(ptr %v4599)
  %v4601 = call ptr @mlf_prim2(i64 8, ptr %v4600, ptr inttoptr (i64 9 to ptr))
  ret ptr %v4601
}

define private ptr @mlf.code.4592(ptr %env, ptr %arg) {
entry:
  %v4593 = getelementptr i8, ptr %env, i64 24
  %v4594 = load ptr, ptr %v4593, align 8, !tbaa !3
  %v4595 = getelementptr i8, ptr %env, i64 32
  %v4596 = load ptr, ptr %v4595, align 8, !tbaa !3
  %v4602 = call ptr @mlf_env_new(i64 1)
  %v4603 = getelementptr i8, ptr %v4602, i64 24
  store ptr %v4596, ptr %v4603, align 8, !tbaa !3
  %v4604 = call ptr @mlf_thunk(ptr @mlf.code.4597, ptr %v4602)
  %v4605 = call ptr @mlf_prim2(i64 32, ptr %v4594, ptr %v4604)
  ret ptr %v4605
}

define private ptr @mlf.code.4642(ptr %env, ptr %arg) {
entry:
  %v4643 = getelementptr i8, ptr %env, i64 24
  %v4644 = load ptr, ptr %v4643, align 8, !tbaa !3
  %v4645 = call ptr @mlf_force(ptr %v4644)
  %v4646 = call ptr @mlf_prim2(i64 8, ptr %v4645, ptr inttoptr (i64 11 to ptr))
  ret ptr %v4646
}

define private ptr @mlf.code.4637(ptr %env, ptr %arg) {
entry:
  %v4638 = getelementptr i8, ptr %env, i64 24
  %v4639 = load ptr, ptr %v4638, align 8, !tbaa !3
  %v4640 = getelementptr i8, ptr %env, i64 32
  %v4641 = load ptr, ptr %v4640, align 8, !tbaa !3
  %v4647 = call ptr @mlf_env_new(i64 1)
  %v4648 = getelementptr i8, ptr %v4647, i64 24
  store ptr %v4641, ptr %v4648, align 8, !tbaa !3
  %v4649 = call ptr @mlf_thunk(ptr @mlf.code.4642, ptr %v4647)
  %v4650 = call ptr @mlf_prim2(i64 32, ptr %v4639, ptr %v4649)
  ret ptr %v4650
}

define private ptr @mlf.code.4697(ptr %env, ptr %arg) {
entry:
  %v4698 = getelementptr i8, ptr %env, i64 24
  %v4699 = load ptr, ptr %v4698, align 8, !tbaa !3
  %v4700 = getelementptr i8, ptr %env, i64 32
  %v4701 = load ptr, ptr %v4700, align 8, !tbaa !3
  %v4702 = getelementptr i8, ptr %env, i64 40
  %v4703 = load ptr, ptr %v4702, align 8, !tbaa !3
  %v4704 = getelementptr i8, ptr %env, i64 48
  %v4705 = load ptr, ptr %v4704, align 8, !tbaa !3
  %v4706 = call ptr @mlf_force(ptr %v4705)
  %v4707 = call ptr @mlf_force(ptr %v4701)
  %v4708 = call ptr @mlf_force(ptr %v4699)
  %v4709 = call ptr @mlf_prim2(i64 20, ptr %v4707, ptr %v4708)
  %v4710 = call ptr @mlf_force(ptr %v4703)
  %v4711 = call ptr @mlf_prim2(i64 20, ptr %v4709, ptr %v4710)
  %v4712 = call ptr @mlf_prim2(i64 19, ptr %v4706, ptr %v4711)
  ret ptr %v4712
}

define private ptr @mlf.code.4719(ptr %env, ptr %arg) {
entry:
  %v4720 = getelementptr i8, ptr %env, i64 24
  %v4721 = load ptr, ptr %v4720, align 8, !tbaa !3
  %v4722 = call ptr @mlf_force(ptr %v4721)
  %v4723 = call ptr @mlf_prim2(i64 8, ptr %v4722, ptr inttoptr (i64 7 to ptr))
  ret ptr %v4723
}

define private ptr @mlf.code.4684(ptr %env, ptr %arg) {
entry:
  %v4685 = getelementptr i8, ptr %env, i64 24
  %v4686 = load ptr, ptr %v4685, align 8, !tbaa !3
  %v4687 = getelementptr i8, ptr %env, i64 32
  %v4688 = load ptr, ptr %v4687, align 8, !tbaa !3
  %v4689 = getelementptr i8, ptr %env, i64 40
  %v4690 = load ptr, ptr %v4689, align 8, !tbaa !3
  %v4691 = getelementptr i8, ptr %env, i64 48
  %v4692 = load ptr, ptr %v4691, align 8, !tbaa !3
  %v4693 = getelementptr i8, ptr %env, i64 56
  %v4694 = load ptr, ptr %v4693, align 8, !tbaa !3
  %v4695 = getelementptr i8, ptr %env, i64 64
  %v4696 = load ptr, ptr %v4695, align 8, !tbaa !3
  %v4713 = call ptr @mlf_env_new(i64 4)
  %v4714 = getelementptr i8, ptr %v4713, i64 24
  store ptr %v4690, ptr %v4714, align 8, !tbaa !3
  %v4715 = getelementptr i8, ptr %v4713, i64 32
  store ptr %v4692, ptr %v4715, align 8, !tbaa !3
  %v4716 = getelementptr i8, ptr %v4713, i64 40
  store ptr %v4694, ptr %v4716, align 8, !tbaa !3
  %v4717 = getelementptr i8, ptr %v4713, i64 48
  store ptr %v4696, ptr %v4717, align 8, !tbaa !3
  %v4718 = call ptr @mlf_thunk(ptr @mlf.code.4697, ptr %v4713)
  %v4724 = call ptr @mlf_env_new(i64 1)
  %v4725 = getelementptr i8, ptr %v4724, i64 24
  store ptr %v4688, ptr %v4725, align 8, !tbaa !3
  %v4726 = call ptr @mlf_thunk(ptr @mlf.code.4719, ptr %v4724)
  %v4727 = call ptr @mlf_prim3(i64 33, ptr %v4686, ptr %v4726, ptr %v4718)
  ret ptr %v4727
}

define private ptr @mlf.code.4778(ptr %env, ptr %arg) {
entry:
  %v4779 = getelementptr i8, ptr %env, i64 24
  %v4780 = load ptr, ptr %v4779, align 8, !tbaa !3
  %v4781 = getelementptr i8, ptr %env, i64 32
  %v4782 = load ptr, ptr %v4781, align 8, !tbaa !3
  %v4783 = getelementptr i8, ptr %env, i64 40
  %v4784 = load ptr, ptr %v4783, align 8, !tbaa !3
  %v4785 = getelementptr i8, ptr %env, i64 48
  %v4786 = load ptr, ptr %v4785, align 8, !tbaa !3
  %v4787 = call ptr @mlf_force(ptr %v4786)
  %v4788 = call ptr @mlf_force(ptr %v4782)
  %v4789 = call ptr @mlf_force(ptr %v4780)
  %v4790 = call ptr @mlf_prim2(i64 20, ptr %v4788, ptr %v4789)
  %v4791 = call ptr @mlf_force(ptr %v4784)
  %v4792 = call ptr @mlf_prim2(i64 20, ptr %v4790, ptr %v4791)
  %v4793 = call ptr @mlf_prim2(i64 19, ptr %v4787, ptr %v4792)
  ret ptr %v4793
}

define private ptr @mlf.code.4800(ptr %env, ptr %arg) {
entry:
  %v4801 = getelementptr i8, ptr %env, i64 24
  %v4802 = load ptr, ptr %v4801, align 8, !tbaa !3
  %v4803 = call ptr @mlf_force(ptr %v4802)
  %v4804 = call ptr @mlf_prim2(i64 8, ptr %v4803, ptr inttoptr (i64 9 to ptr))
  ret ptr %v4804
}

define private ptr @mlf.code.4765(ptr %env, ptr %arg) {
entry:
  %v4766 = getelementptr i8, ptr %env, i64 24
  %v4767 = load ptr, ptr %v4766, align 8, !tbaa !3
  %v4768 = getelementptr i8, ptr %env, i64 32
  %v4769 = load ptr, ptr %v4768, align 8, !tbaa !3
  %v4770 = getelementptr i8, ptr %env, i64 40
  %v4771 = load ptr, ptr %v4770, align 8, !tbaa !3
  %v4772 = getelementptr i8, ptr %env, i64 48
  %v4773 = load ptr, ptr %v4772, align 8, !tbaa !3
  %v4774 = getelementptr i8, ptr %env, i64 56
  %v4775 = load ptr, ptr %v4774, align 8, !tbaa !3
  %v4776 = getelementptr i8, ptr %env, i64 64
  %v4777 = load ptr, ptr %v4776, align 8, !tbaa !3
  %v4794 = call ptr @mlf_env_new(i64 4)
  %v4795 = getelementptr i8, ptr %v4794, i64 24
  store ptr %v4771, ptr %v4795, align 8, !tbaa !3
  %v4796 = getelementptr i8, ptr %v4794, i64 32
  store ptr %v4773, ptr %v4796, align 8, !tbaa !3
  %v4797 = getelementptr i8, ptr %v4794, i64 40
  store ptr %v4775, ptr %v4797, align 8, !tbaa !3
  %v4798 = getelementptr i8, ptr %v4794, i64 48
  store ptr %v4777, ptr %v4798, align 8, !tbaa !3
  %v4799 = call ptr @mlf_thunk(ptr @mlf.code.4778, ptr %v4794)
  %v4805 = call ptr @mlf_env_new(i64 1)
  %v4806 = getelementptr i8, ptr %v4805, i64 24
  store ptr %v4769, ptr %v4806, align 8, !tbaa !3
  %v4807 = call ptr @mlf_thunk(ptr @mlf.code.4800, ptr %v4805)
  %v4808 = call ptr @mlf_prim3(i64 33, ptr %v4767, ptr %v4807, ptr %v4799)
  ret ptr %v4808
}

define private ptr @mlf.code.4857(ptr %env, ptr %arg) {
entry:
  %v4858 = getelementptr i8, ptr %env, i64 24
  %v4859 = load ptr, ptr %v4858, align 8, !tbaa !3
  %v4860 = getelementptr i8, ptr %env, i64 32
  %v4861 = load ptr, ptr %v4860, align 8, !tbaa !3
  %v4862 = getelementptr i8, ptr %env, i64 40
  %v4863 = load ptr, ptr %v4862, align 8, !tbaa !3
  %v4864 = getelementptr i8, ptr %env, i64 48
  %v4865 = load ptr, ptr %v4864, align 8, !tbaa !3
  %v4866 = call ptr @mlf_force(ptr %v4865)
  %v4867 = call ptr @mlf_force(ptr %v4861)
  %v4868 = call ptr @mlf_force(ptr %v4859)
  %v4869 = call ptr @mlf_prim2(i64 20, ptr %v4867, ptr %v4868)
  %v4870 = call ptr @mlf_force(ptr %v4863)
  %v4871 = call ptr @mlf_prim2(i64 20, ptr %v4869, ptr %v4870)
  %v4872 = call ptr @mlf_prim2(i64 19, ptr %v4866, ptr %v4871)
  ret ptr %v4872
}

define private ptr @mlf.code.4879(ptr %env, ptr %arg) {
entry:
  %v4880 = getelementptr i8, ptr %env, i64 24
  %v4881 = load ptr, ptr %v4880, align 8, !tbaa !3
  %v4882 = call ptr @mlf_force(ptr %v4881)
  %v4883 = call ptr @mlf_prim2(i64 8, ptr %v4882, ptr inttoptr (i64 11 to ptr))
  ret ptr %v4883
}

define private ptr @mlf.code.4844(ptr %env, ptr %arg) {
entry:
  %v4845 = getelementptr i8, ptr %env, i64 24
  %v4846 = load ptr, ptr %v4845, align 8, !tbaa !3
  %v4847 = getelementptr i8, ptr %env, i64 32
  %v4848 = load ptr, ptr %v4847, align 8, !tbaa !3
  %v4849 = getelementptr i8, ptr %env, i64 40
  %v4850 = load ptr, ptr %v4849, align 8, !tbaa !3
  %v4851 = getelementptr i8, ptr %env, i64 48
  %v4852 = load ptr, ptr %v4851, align 8, !tbaa !3
  %v4853 = getelementptr i8, ptr %env, i64 56
  %v4854 = load ptr, ptr %v4853, align 8, !tbaa !3
  %v4855 = getelementptr i8, ptr %env, i64 64
  %v4856 = load ptr, ptr %v4855, align 8, !tbaa !3
  %v4873 = call ptr @mlf_env_new(i64 4)
  %v4874 = getelementptr i8, ptr %v4873, i64 24
  store ptr %v4850, ptr %v4874, align 8, !tbaa !3
  %v4875 = getelementptr i8, ptr %v4873, i64 32
  store ptr %v4852, ptr %v4875, align 8, !tbaa !3
  %v4876 = getelementptr i8, ptr %v4873, i64 40
  store ptr %v4854, ptr %v4876, align 8, !tbaa !3
  %v4877 = getelementptr i8, ptr %v4873, i64 48
  store ptr %v4856, ptr %v4877, align 8, !tbaa !3
  %v4878 = call ptr @mlf_thunk(ptr @mlf.code.4857, ptr %v4873)
  %v4884 = call ptr @mlf_env_new(i64 1)
  %v4885 = getelementptr i8, ptr %v4884, i64 24
  store ptr %v4848, ptr %v4885, align 8, !tbaa !3
  %v4886 = call ptr @mlf_thunk(ptr @mlf.code.4879, ptr %v4884)
  %v4887 = call ptr @mlf_prim3(i64 33, ptr %v4846, ptr %v4886, ptr %v4878)
  ret ptr %v4887
}

define private ptr @mlf.code.4932(ptr %env, ptr %arg) {
entry:
  %v4933 = getelementptr i8, ptr %env, i64 24
  %v4934 = load ptr, ptr %v4933, align 8, !tbaa !3
  %v4935 = getelementptr i8, ptr %env, i64 32
  %v4936 = load ptr, ptr %v4935, align 8, !tbaa !3
  %v4937 = getelementptr i8, ptr %env, i64 40
  %v4938 = load ptr, ptr %v4937, align 8, !tbaa !3
  %v4939 = getelementptr i8, ptr %env, i64 48
  %v4940 = load ptr, ptr %v4939, align 8, !tbaa !3
  %v4941 = call ptr @mlf_force(ptr %v4940)
  %v4942 = call ptr @mlf_force(ptr %v4936)
  %v4943 = call ptr @mlf_force(ptr %v4934)
  %v4944 = call ptr @mlf_prim2(i64 20, ptr %v4942, ptr %v4943)
  %v4945 = call ptr @mlf_force(ptr %v4938)
  %v4946 = call ptr @mlf_prim2(i64 20, ptr %v4944, ptr %v4945)
  %v4947 = call ptr @mlf_prim2(i64 18, ptr %v4941, ptr %v4946)
  ret ptr %v4947
}

define private ptr @mlf.code.4954(ptr %env, ptr %arg) {
entry:
  %v4955 = getelementptr i8, ptr %env, i64 24
  %v4956 = load ptr, ptr %v4955, align 8, !tbaa !3
  %v4957 = call ptr @mlf_force(ptr %v4956)
  %v4958 = call ptr @mlf_prim2(i64 8, ptr %v4957, ptr inttoptr (i64 7 to ptr))
  ret ptr %v4958
}

define private ptr @mlf.code.4919(ptr %env, ptr %arg) {
entry:
  %v4920 = getelementptr i8, ptr %env, i64 24
  %v4921 = load ptr, ptr %v4920, align 8, !tbaa !3
  %v4922 = getelementptr i8, ptr %env, i64 32
  %v4923 = load ptr, ptr %v4922, align 8, !tbaa !3
  %v4924 = getelementptr i8, ptr %env, i64 40
  %v4925 = load ptr, ptr %v4924, align 8, !tbaa !3
  %v4926 = getelementptr i8, ptr %env, i64 48
  %v4927 = load ptr, ptr %v4926, align 8, !tbaa !3
  %v4928 = getelementptr i8, ptr %env, i64 56
  %v4929 = load ptr, ptr %v4928, align 8, !tbaa !3
  %v4930 = getelementptr i8, ptr %env, i64 64
  %v4931 = load ptr, ptr %v4930, align 8, !tbaa !3
  %v4948 = call ptr @mlf_env_new(i64 4)
  %v4949 = getelementptr i8, ptr %v4948, i64 24
  store ptr %v4925, ptr %v4949, align 8, !tbaa !3
  %v4950 = getelementptr i8, ptr %v4948, i64 32
  store ptr %v4927, ptr %v4950, align 8, !tbaa !3
  %v4951 = getelementptr i8, ptr %v4948, i64 40
  store ptr %v4929, ptr %v4951, align 8, !tbaa !3
  %v4952 = getelementptr i8, ptr %v4948, i64 48
  store ptr %v4931, ptr %v4952, align 8, !tbaa !3
  %v4953 = call ptr @mlf_thunk(ptr @mlf.code.4932, ptr %v4948)
  %v4959 = call ptr @mlf_env_new(i64 1)
  %v4960 = getelementptr i8, ptr %v4959, i64 24
  store ptr %v4923, ptr %v4960, align 8, !tbaa !3
  %v4961 = call ptr @mlf_thunk(ptr @mlf.code.4954, ptr %v4959)
  %v4962 = call ptr @mlf_prim3(i64 33, ptr %v4921, ptr %v4961, ptr %v4953)
  ret ptr %v4962
}

define private ptr @mlf.code.5003(ptr %env, ptr %arg) {
entry:
  %v5004 = getelementptr i8, ptr %env, i64 24
  %v5005 = load ptr, ptr %v5004, align 8, !tbaa !3
  %v5006 = getelementptr i8, ptr %env, i64 32
  %v5007 = load ptr, ptr %v5006, align 8, !tbaa !3
  %v5008 = getelementptr i8, ptr %env, i64 40
  %v5009 = load ptr, ptr %v5008, align 8, !tbaa !3
  %v5010 = getelementptr i8, ptr %env, i64 48
  %v5011 = load ptr, ptr %v5010, align 8, !tbaa !3
  %v5012 = call ptr @mlf_force(ptr %v5011)
  %v5013 = call ptr @mlf_force(ptr %v5007)
  %v5014 = call ptr @mlf_force(ptr %v5005)
  %v5015 = call ptr @mlf_prim2(i64 20, ptr %v5013, ptr %v5014)
  %v5016 = call ptr @mlf_force(ptr %v5009)
  %v5017 = call ptr @mlf_prim2(i64 20, ptr %v5015, ptr %v5016)
  %v5018 = call ptr @mlf_prim2(i64 18, ptr %v5012, ptr %v5017)
  ret ptr %v5018
}

define private ptr @mlf.code.5025(ptr %env, ptr %arg) {
entry:
  %v5026 = getelementptr i8, ptr %env, i64 24
  %v5027 = load ptr, ptr %v5026, align 8, !tbaa !3
  %v5028 = call ptr @mlf_force(ptr %v5027)
  %v5029 = call ptr @mlf_prim2(i64 8, ptr %v5028, ptr inttoptr (i64 9 to ptr))
  ret ptr %v5029
}

define private ptr @mlf.code.4990(ptr %env, ptr %arg) {
entry:
  %v4991 = getelementptr i8, ptr %env, i64 24
  %v4992 = load ptr, ptr %v4991, align 8, !tbaa !3
  %v4993 = getelementptr i8, ptr %env, i64 32
  %v4994 = load ptr, ptr %v4993, align 8, !tbaa !3
  %v4995 = getelementptr i8, ptr %env, i64 40
  %v4996 = load ptr, ptr %v4995, align 8, !tbaa !3
  %v4997 = getelementptr i8, ptr %env, i64 48
  %v4998 = load ptr, ptr %v4997, align 8, !tbaa !3
  %v4999 = getelementptr i8, ptr %env, i64 56
  %v5000 = load ptr, ptr %v4999, align 8, !tbaa !3
  %v5001 = getelementptr i8, ptr %env, i64 64
  %v5002 = load ptr, ptr %v5001, align 8, !tbaa !3
  %v5019 = call ptr @mlf_env_new(i64 4)
  %v5020 = getelementptr i8, ptr %v5019, i64 24
  store ptr %v4996, ptr %v5020, align 8, !tbaa !3
  %v5021 = getelementptr i8, ptr %v5019, i64 32
  store ptr %v4998, ptr %v5021, align 8, !tbaa !3
  %v5022 = getelementptr i8, ptr %v5019, i64 40
  store ptr %v5000, ptr %v5022, align 8, !tbaa !3
  %v5023 = getelementptr i8, ptr %v5019, i64 48
  store ptr %v5002, ptr %v5023, align 8, !tbaa !3
  %v5024 = call ptr @mlf_thunk(ptr @mlf.code.5003, ptr %v5019)
  %v5030 = call ptr @mlf_env_new(i64 1)
  %v5031 = getelementptr i8, ptr %v5030, i64 24
  store ptr %v4994, ptr %v5031, align 8, !tbaa !3
  %v5032 = call ptr @mlf_thunk(ptr @mlf.code.5025, ptr %v5030)
  %v5033 = call ptr @mlf_prim3(i64 33, ptr %v4992, ptr %v5032, ptr %v5024)
  ret ptr %v5033
}

define private ptr @mlf.code.5070(ptr %env, ptr %arg) {
entry:
  %v5071 = getelementptr i8, ptr %env, i64 24
  %v5072 = load ptr, ptr %v5071, align 8, !tbaa !3
  %v5073 = getelementptr i8, ptr %env, i64 32
  %v5074 = load ptr, ptr %v5073, align 8, !tbaa !3
  %v5075 = getelementptr i8, ptr %env, i64 40
  %v5076 = load ptr, ptr %v5075, align 8, !tbaa !3
  %v5077 = getelementptr i8, ptr %env, i64 48
  %v5078 = load ptr, ptr %v5077, align 8, !tbaa !3
  %v5079 = call ptr @mlf_force(ptr %v5078)
  %v5080 = call ptr @mlf_force(ptr %v5074)
  %v5081 = call ptr @mlf_force(ptr %v5072)
  %v5082 = call ptr @mlf_prim2(i64 20, ptr %v5080, ptr %v5081)
  %v5083 = call ptr @mlf_force(ptr %v5076)
  %v5084 = call ptr @mlf_prim2(i64 20, ptr %v5082, ptr %v5083)
  %v5085 = call ptr @mlf_prim2(i64 18, ptr %v5079, ptr %v5084)
  ret ptr %v5085
}

define private ptr @mlf.code.5092(ptr %env, ptr %arg) {
entry:
  %v5093 = getelementptr i8, ptr %env, i64 24
  %v5094 = load ptr, ptr %v5093, align 8, !tbaa !3
  %v5095 = call ptr @mlf_force(ptr %v5094)
  %v5096 = call ptr @mlf_prim2(i64 8, ptr %v5095, ptr inttoptr (i64 11 to ptr))
  ret ptr %v5096
}

define private ptr @mlf.code.5057(ptr %env, ptr %arg) {
entry:
  %v5058 = getelementptr i8, ptr %env, i64 24
  %v5059 = load ptr, ptr %v5058, align 8, !tbaa !3
  %v5060 = getelementptr i8, ptr %env, i64 32
  %v5061 = load ptr, ptr %v5060, align 8, !tbaa !3
  %v5062 = getelementptr i8, ptr %env, i64 40
  %v5063 = load ptr, ptr %v5062, align 8, !tbaa !3
  %v5064 = getelementptr i8, ptr %env, i64 48
  %v5065 = load ptr, ptr %v5064, align 8, !tbaa !3
  %v5066 = getelementptr i8, ptr %env, i64 56
  %v5067 = load ptr, ptr %v5066, align 8, !tbaa !3
  %v5068 = getelementptr i8, ptr %env, i64 64
  %v5069 = load ptr, ptr %v5068, align 8, !tbaa !3
  %v5086 = call ptr @mlf_env_new(i64 4)
  %v5087 = getelementptr i8, ptr %v5086, i64 24
  store ptr %v5063, ptr %v5087, align 8, !tbaa !3
  %v5088 = getelementptr i8, ptr %v5086, i64 32
  store ptr %v5065, ptr %v5088, align 8, !tbaa !3
  %v5089 = getelementptr i8, ptr %v5086, i64 40
  store ptr %v5067, ptr %v5089, align 8, !tbaa !3
  %v5090 = getelementptr i8, ptr %v5086, i64 48
  store ptr %v5069, ptr %v5090, align 8, !tbaa !3
  %v5091 = call ptr @mlf_thunk(ptr @mlf.code.5070, ptr %v5086)
  %v5097 = call ptr @mlf_env_new(i64 1)
  %v5098 = getelementptr i8, ptr %v5097, i64 24
  store ptr %v5061, ptr %v5098, align 8, !tbaa !3
  %v5099 = call ptr @mlf_thunk(ptr @mlf.code.5092, ptr %v5097)
  %v5100 = call ptr @mlf_prim3(i64 33, ptr %v5059, ptr %v5099, ptr %v5091)
  ret ptr %v5100
}

define private ptr @mlf.code.5109(ptr %env, ptr %arg) {
entry:
  %v5110 = getelementptr i8, ptr %env, i64 24
  %v5111 = load ptr, ptr %v5110, align 8, !tbaa !3
  %v5112 = getelementptr i8, ptr %env, i64 32
  %v5113 = load ptr, ptr %v5112, align 8, !tbaa !3
  %v5114 = getelementptr i8, ptr %env, i64 40
  %v5115 = load ptr, ptr %v5114, align 8, !tbaa !3
  %v5116 = call ptr @mlf_force(ptr %v5115)
  %v5117 = call ptr @mlf_prim2(i64 8, ptr %v5116, ptr inttoptr (i64 15 to ptr))
  %v5118 = call ptr @mlf_env_new(i64 3)
  %v5119 = getelementptr i8, ptr %v5118, i64 24
  store ptr %v5111, ptr %v5119, align 8, !tbaa !3
  %v5120 = getelementptr i8, ptr %v5118, i64 32
  store ptr %v5113, ptr %v5120, align 8, !tbaa !3
  %v5121 = getelementptr i8, ptr %v5118, i64 40
  store ptr %v5117, ptr %v5121, align 8, !tbaa !3
  %v5122 = call ptr @mlf_native_io(ptr @mlf.numeric.entry.4081, ptr %v5118)
  ret ptr %v5122
}

define private ptr @mlf.code.5042(ptr %env, ptr %arg) {
entry:
  %v5043 = getelementptr i8, ptr %env, i64 24
  %v5044 = load ptr, ptr %v5043, align 8, !tbaa !3
  %v5045 = getelementptr i8, ptr %env, i64 32
  %v5046 = load ptr, ptr %v5045, align 8, !tbaa !3
  %v5047 = getelementptr i8, ptr %env, i64 40
  %v5048 = load ptr, ptr %v5047, align 8, !tbaa !3
  %v5049 = getelementptr i8, ptr %env, i64 48
  %v5050 = load ptr, ptr %v5049, align 8, !tbaa !3
  %v5051 = getelementptr i8, ptr %env, i64 56
  %v5052 = load ptr, ptr %v5051, align 8, !tbaa !3
  %v5053 = getelementptr i8, ptr %env, i64 64
  %v5054 = load ptr, ptr %v5053, align 8, !tbaa !3
  %v5055 = getelementptr i8, ptr %env, i64 72
  %v5056 = load ptr, ptr %v5055, align 8, !tbaa !3
  %v5101 = call ptr @mlf_env_new(i64 6)
  %v5102 = getelementptr i8, ptr %v5101, i64 24
  store ptr %v5044, ptr %v5102, align 8, !tbaa !3
  %v5103 = getelementptr i8, ptr %v5101, i64 32
  store ptr %v5048, ptr %v5103, align 8, !tbaa !3
  %v5104 = getelementptr i8, ptr %v5101, i64 40
  store ptr %v5050, ptr %v5104, align 8, !tbaa !3
  %v5105 = getelementptr i8, ptr %v5101, i64 48
  store ptr %v5052, ptr %v5105, align 8, !tbaa !3
  %v5106 = getelementptr i8, ptr %v5101, i64 56
  store ptr %v5054, ptr %v5106, align 8, !tbaa !3
  %v5107 = getelementptr i8, ptr %v5101, i64 64
  store ptr %v5056, ptr %v5107, align 8, !tbaa !3
  %v5108 = call ptr @mlf_thunk(ptr @mlf.code.5057, ptr %v5101)
  %v5123 = call ptr @mlf_env_new(i64 3)
  %v5124 = getelementptr i8, ptr %v5123, i64 24
  store ptr %v5044, ptr %v5124, align 8, !tbaa !3
  %v5125 = getelementptr i8, ptr %v5123, i64 32
  store ptr %v5046, ptr %v5125, align 8, !tbaa !3
  %v5126 = getelementptr i8, ptr %v5123, i64 40
  store ptr %v5048, ptr %v5126, align 8, !tbaa !3
  %v5127 = call ptr @mlf_closure(ptr @mlf.code.5109, ptr %v5123)
  %v5128 = call ptr @mlf_prim2(i64 1, ptr %v5108, ptr %v5127)
  ret ptr %v5128
}

define private ptr @mlf.code.4971(ptr %env, ptr %arg) {
entry:
  %v4972 = getelementptr i8, ptr %env, i64 24
  %v4973 = load ptr, ptr %v4972, align 8, !tbaa !3
  %v4974 = getelementptr i8, ptr %env, i64 32
  %v4975 = load ptr, ptr %v4974, align 8, !tbaa !3
  %v4976 = getelementptr i8, ptr %env, i64 40
  %v4977 = load ptr, ptr %v4976, align 8, !tbaa !3
  %v4978 = getelementptr i8, ptr %env, i64 48
  %v4979 = load ptr, ptr %v4978, align 8, !tbaa !3
  %v4980 = getelementptr i8, ptr %env, i64 56
  %v4981 = load ptr, ptr %v4980, align 8, !tbaa !3
  %v4982 = getelementptr i8, ptr %env, i64 64
  %v4983 = load ptr, ptr %v4982, align 8, !tbaa !3
  %v4984 = getelementptr i8, ptr %env, i64 72
  %v4985 = load ptr, ptr %v4984, align 8, !tbaa !3
  %v4986 = getelementptr i8, ptr %env, i64 80
  %v4987 = load ptr, ptr %v4986, align 8, !tbaa !3
  %v4988 = getelementptr i8, ptr %env, i64 88
  %v4989 = load ptr, ptr %v4988, align 8, !tbaa !3
  %v5034 = call ptr @mlf_env_new(i64 6)
  %v5035 = getelementptr i8, ptr %v5034, i64 24
  store ptr %v4973, ptr %v5035, align 8, !tbaa !3
  %v5036 = getelementptr i8, ptr %v5034, i64 32
  store ptr %v4977, ptr %v5036, align 8, !tbaa !3
  %v5037 = getelementptr i8, ptr %v5034, i64 40
  store ptr %v4979, ptr %v5037, align 8, !tbaa !3
  %v5038 = getelementptr i8, ptr %v5034, i64 48
  store ptr %v4981, ptr %v5038, align 8, !tbaa !3
  %v5039 = getelementptr i8, ptr %v5034, i64 56
  store ptr %v4985, ptr %v5039, align 8, !tbaa !3
  %v5040 = getelementptr i8, ptr %v5034, i64 64
  store ptr %v4987, ptr %v5040, align 8, !tbaa !3
  %v5041 = call ptr @mlf_thunk(ptr @mlf.code.4990, ptr %v5034)
  %v5129 = call ptr @mlf_env_new(i64 7)
  %v5130 = getelementptr i8, ptr %v5129, i64 24
  store ptr %v4973, ptr %v5130, align 8, !tbaa !3
  %v5131 = getelementptr i8, ptr %v5129, i64 32
  store ptr %v4975, ptr %v5131, align 8, !tbaa !3
  %v5132 = getelementptr i8, ptr %v5129, i64 40
  store ptr %v4977, ptr %v5132, align 8, !tbaa !3
  %v5133 = getelementptr i8, ptr %v5129, i64 48
  store ptr %v4979, ptr %v5133, align 8, !tbaa !3
  %v5134 = getelementptr i8, ptr %v5129, i64 56
  store ptr %v4983, ptr %v5134, align 8, !tbaa !3
  %v5135 = getelementptr i8, ptr %v5129, i64 64
  store ptr %v4985, ptr %v5135, align 8, !tbaa !3
  %v5136 = getelementptr i8, ptr %v5129, i64 72
  store ptr %v4989, ptr %v5136, align 8, !tbaa !3
  %v5137 = call ptr @mlf_closure(ptr @mlf.code.5042, ptr %v5129)
  %v5138 = call ptr @mlf_prim2(i64 1, ptr %v5041, ptr %v5137)
  ret ptr %v5138
}

define private ptr @mlf.code.4896(ptr %env, ptr %arg) {
entry:
  %v4897 = getelementptr i8, ptr %env, i64 24
  %v4898 = load ptr, ptr %v4897, align 8, !tbaa !3
  %v4899 = getelementptr i8, ptr %env, i64 32
  %v4900 = load ptr, ptr %v4899, align 8, !tbaa !3
  %v4901 = getelementptr i8, ptr %env, i64 40
  %v4902 = load ptr, ptr %v4901, align 8, !tbaa !3
  %v4903 = getelementptr i8, ptr %env, i64 48
  %v4904 = load ptr, ptr %v4903, align 8, !tbaa !3
  %v4905 = getelementptr i8, ptr %env, i64 56
  %v4906 = load ptr, ptr %v4905, align 8, !tbaa !3
  %v4907 = getelementptr i8, ptr %env, i64 64
  %v4908 = load ptr, ptr %v4907, align 8, !tbaa !3
  %v4909 = getelementptr i8, ptr %env, i64 72
  %v4910 = load ptr, ptr %v4909, align 8, !tbaa !3
  %v4911 = getelementptr i8, ptr %env, i64 80
  %v4912 = load ptr, ptr %v4911, align 8, !tbaa !3
  %v4913 = getelementptr i8, ptr %env, i64 88
  %v4914 = load ptr, ptr %v4913, align 8, !tbaa !3
  %v4915 = getelementptr i8, ptr %env, i64 96
  %v4916 = load ptr, ptr %v4915, align 8, !tbaa !3
  %v4917 = getelementptr i8, ptr %env, i64 104
  %v4918 = load ptr, ptr %v4917, align 8, !tbaa !3
  %v4963 = call ptr @mlf_env_new(i64 6)
  %v4964 = getelementptr i8, ptr %v4963, i64 24
  store ptr %v4898, ptr %v4964, align 8, !tbaa !3
  %v4965 = getelementptr i8, ptr %v4963, i64 32
  store ptr %v4902, ptr %v4965, align 8, !tbaa !3
  %v4966 = getelementptr i8, ptr %v4963, i64 40
  store ptr %v4904, ptr %v4966, align 8, !tbaa !3
  %v4967 = getelementptr i8, ptr %v4963, i64 48
  store ptr %v4906, ptr %v4967, align 8, !tbaa !3
  %v4968 = getelementptr i8, ptr %v4963, i64 56
  store ptr %v4912, ptr %v4968, align 8, !tbaa !3
  %v4969 = getelementptr i8, ptr %v4963, i64 64
  store ptr %v4914, ptr %v4969, align 8, !tbaa !3
  %v4970 = call ptr @mlf_thunk(ptr @mlf.code.4919, ptr %v4963)
  %v5139 = call ptr @mlf_env_new(i64 9)
  %v5140 = getelementptr i8, ptr %v5139, i64 24
  store ptr %v4898, ptr %v5140, align 8, !tbaa !3
  %v5141 = getelementptr i8, ptr %v5139, i64 32
  store ptr %v4900, ptr %v5141, align 8, !tbaa !3
  %v5142 = getelementptr i8, ptr %v5139, i64 40
  store ptr %v4902, ptr %v5142, align 8, !tbaa !3
  %v5143 = getelementptr i8, ptr %v5139, i64 48
  store ptr %v4904, ptr %v5143, align 8, !tbaa !3
  %v5144 = getelementptr i8, ptr %v5139, i64 56
  store ptr %v4908, ptr %v5144, align 8, !tbaa !3
  %v5145 = getelementptr i8, ptr %v5139, i64 64
  store ptr %v4910, ptr %v5145, align 8, !tbaa !3
  %v5146 = getelementptr i8, ptr %v5139, i64 72
  store ptr %v4912, ptr %v5146, align 8, !tbaa !3
  %v5147 = getelementptr i8, ptr %v5139, i64 80
  store ptr %v4916, ptr %v5147, align 8, !tbaa !3
  %v5148 = getelementptr i8, ptr %v5139, i64 88
  store ptr %v4918, ptr %v5148, align 8, !tbaa !3
  %v5149 = call ptr @mlf_closure(ptr @mlf.code.4971, ptr %v5139)
  %v5150 = call ptr @mlf_prim2(i64 1, ptr %v4970, ptr %v5149)
  ret ptr %v5150
}

define private ptr @mlf.code.4817(ptr %env, ptr %arg) {
entry:
  %v4818 = getelementptr i8, ptr %env, i64 24
  %v4819 = load ptr, ptr %v4818, align 8, !tbaa !3
  %v4820 = getelementptr i8, ptr %env, i64 32
  %v4821 = load ptr, ptr %v4820, align 8, !tbaa !3
  %v4822 = getelementptr i8, ptr %env, i64 40
  %v4823 = load ptr, ptr %v4822, align 8, !tbaa !3
  %v4824 = getelementptr i8, ptr %env, i64 48
  %v4825 = load ptr, ptr %v4824, align 8, !tbaa !3
  %v4826 = getelementptr i8, ptr %env, i64 56
  %v4827 = load ptr, ptr %v4826, align 8, !tbaa !3
  %v4828 = getelementptr i8, ptr %env, i64 64
  %v4829 = load ptr, ptr %v4828, align 8, !tbaa !3
  %v4830 = getelementptr i8, ptr %env, i64 72
  %v4831 = load ptr, ptr %v4830, align 8, !tbaa !3
  %v4832 = getelementptr i8, ptr %env, i64 80
  %v4833 = load ptr, ptr %v4832, align 8, !tbaa !3
  %v4834 = getelementptr i8, ptr %env, i64 88
  %v4835 = load ptr, ptr %v4834, align 8, !tbaa !3
  %v4836 = getelementptr i8, ptr %env, i64 96
  %v4837 = load ptr, ptr %v4836, align 8, !tbaa !3
  %v4838 = getelementptr i8, ptr %env, i64 104
  %v4839 = load ptr, ptr %v4838, align 8, !tbaa !3
  %v4840 = getelementptr i8, ptr %env, i64 112
  %v4841 = load ptr, ptr %v4840, align 8, !tbaa !3
  %v4842 = getelementptr i8, ptr %env, i64 120
  %v4843 = load ptr, ptr %v4842, align 8, !tbaa !3
  %v4888 = call ptr @mlf_env_new(i64 6)
  %v4889 = getelementptr i8, ptr %v4888, i64 24
  store ptr %v4819, ptr %v4889, align 8, !tbaa !3
  %v4890 = getelementptr i8, ptr %v4888, i64 32
  store ptr %v4821, ptr %v4890, align 8, !tbaa !3
  %v4891 = getelementptr i8, ptr %v4888, i64 40
  store ptr %v4827, ptr %v4891, align 8, !tbaa !3
  %v4892 = getelementptr i8, ptr %v4888, i64 48
  store ptr %v4833, ptr %v4892, align 8, !tbaa !3
  %v4893 = getelementptr i8, ptr %v4888, i64 56
  store ptr %v4835, ptr %v4893, align 8, !tbaa !3
  %v4894 = getelementptr i8, ptr %v4888, i64 64
  store ptr %v4837, ptr %v4894, align 8, !tbaa !3
  %v4895 = call ptr @mlf_thunk(ptr @mlf.code.4844, ptr %v4888)
  %v5151 = call ptr @mlf_env_new(i64 11)
  %v5152 = getelementptr i8, ptr %v5151, i64 24
  store ptr %v4819, ptr %v5152, align 8, !tbaa !3
  %v5153 = getelementptr i8, ptr %v5151, i64 32
  store ptr %v4821, ptr %v5153, align 8, !tbaa !3
  %v5154 = getelementptr i8, ptr %v5151, i64 40
  store ptr %v4823, ptr %v5154, align 8, !tbaa !3
  %v5155 = getelementptr i8, ptr %v5151, i64 48
  store ptr %v4825, ptr %v5155, align 8, !tbaa !3
  %v5156 = getelementptr i8, ptr %v5151, i64 56
  store ptr %v4829, ptr %v5156, align 8, !tbaa !3
  %v5157 = getelementptr i8, ptr %v5151, i64 64
  store ptr %v4831, ptr %v5157, align 8, !tbaa !3
  %v5158 = getelementptr i8, ptr %v5151, i64 72
  store ptr %v4833, ptr %v5158, align 8, !tbaa !3
  %v5159 = getelementptr i8, ptr %v5151, i64 80
  store ptr %v4835, ptr %v5159, align 8, !tbaa !3
  %v5160 = getelementptr i8, ptr %v5151, i64 88
  store ptr %v4839, ptr %v5160, align 8, !tbaa !3
  %v5161 = getelementptr i8, ptr %v5151, i64 96
  store ptr %v4841, ptr %v5161, align 8, !tbaa !3
  %v5162 = getelementptr i8, ptr %v5151, i64 104
  store ptr %v4843, ptr %v5162, align 8, !tbaa !3
  %v5163 = call ptr @mlf_closure(ptr @mlf.code.4896, ptr %v5151)
  %v5164 = call ptr @mlf_prim2(i64 1, ptr %v4895, ptr %v5163)
  ret ptr %v5164
}

define private ptr @mlf.code.4736(ptr %env, ptr %arg) {
entry:
  %v4737 = getelementptr i8, ptr %env, i64 24
  %v4738 = load ptr, ptr %v4737, align 8, !tbaa !3
  %v4739 = getelementptr i8, ptr %env, i64 32
  %v4740 = load ptr, ptr %v4739, align 8, !tbaa !3
  %v4741 = getelementptr i8, ptr %env, i64 40
  %v4742 = load ptr, ptr %v4741, align 8, !tbaa !3
  %v4743 = getelementptr i8, ptr %env, i64 48
  %v4744 = load ptr, ptr %v4743, align 8, !tbaa !3
  %v4745 = getelementptr i8, ptr %env, i64 56
  %v4746 = load ptr, ptr %v4745, align 8, !tbaa !3
  %v4747 = getelementptr i8, ptr %env, i64 64
  %v4748 = load ptr, ptr %v4747, align 8, !tbaa !3
  %v4749 = getelementptr i8, ptr %env, i64 72
  %v4750 = load ptr, ptr %v4749, align 8, !tbaa !3
  %v4751 = getelementptr i8, ptr %env, i64 80
  %v4752 = load ptr, ptr %v4751, align 8, !tbaa !3
  %v4753 = getelementptr i8, ptr %env, i64 88
  %v4754 = load ptr, ptr %v4753, align 8, !tbaa !3
  %v4755 = getelementptr i8, ptr %env, i64 96
  %v4756 = load ptr, ptr %v4755, align 8, !tbaa !3
  %v4757 = getelementptr i8, ptr %env, i64 104
  %v4758 = load ptr, ptr %v4757, align 8, !tbaa !3
  %v4759 = getelementptr i8, ptr %env, i64 112
  %v4760 = load ptr, ptr %v4759, align 8, !tbaa !3
  %v4761 = getelementptr i8, ptr %env, i64 120
  %v4762 = load ptr, ptr %v4761, align 8, !tbaa !3
  %v4763 = getelementptr i8, ptr %env, i64 128
  %v4764 = load ptr, ptr %v4763, align 8, !tbaa !3
  %v4809 = call ptr @mlf_env_new(i64 6)
  %v4810 = getelementptr i8, ptr %v4809, i64 24
  store ptr %v4738, ptr %v4810, align 8, !tbaa !3
  %v4811 = getelementptr i8, ptr %v4809, i64 32
  store ptr %v4740, ptr %v4811, align 8, !tbaa !3
  %v4812 = getelementptr i8, ptr %v4809, i64 40
  store ptr %v4746, ptr %v4812, align 8, !tbaa !3
  %v4813 = getelementptr i8, ptr %v4809, i64 48
  store ptr %v4750, ptr %v4813, align 8, !tbaa !3
  %v4814 = getelementptr i8, ptr %v4809, i64 56
  store ptr %v4754, ptr %v4814, align 8, !tbaa !3
  %v4815 = getelementptr i8, ptr %v4809, i64 64
  store ptr %v4756, ptr %v4815, align 8, !tbaa !3
  %v4816 = call ptr @mlf_thunk(ptr @mlf.code.4765, ptr %v4809)
  %v5165 = call ptr @mlf_env_new(i64 13)
  %v5166 = getelementptr i8, ptr %v5165, i64 24
  store ptr %v4738, ptr %v5166, align 8, !tbaa !3
  %v5167 = getelementptr i8, ptr %v5165, i64 32
  store ptr %v4740, ptr %v5167, align 8, !tbaa !3
  %v5168 = getelementptr i8, ptr %v5165, i64 40
  store ptr %v4742, ptr %v5168, align 8, !tbaa !3
  %v5169 = getelementptr i8, ptr %v5165, i64 48
  store ptr %v4744, ptr %v5169, align 8, !tbaa !3
  %v5170 = getelementptr i8, ptr %v5165, i64 56
  store ptr %v4746, ptr %v5170, align 8, !tbaa !3
  %v5171 = getelementptr i8, ptr %v5165, i64 64
  store ptr %v4748, ptr %v5171, align 8, !tbaa !3
  %v5172 = getelementptr i8, ptr %v5165, i64 72
  store ptr %v4750, ptr %v5172, align 8, !tbaa !3
  %v5173 = getelementptr i8, ptr %v5165, i64 80
  store ptr %v4752, ptr %v5173, align 8, !tbaa !3
  %v5174 = getelementptr i8, ptr %v5165, i64 88
  store ptr %v4754, ptr %v5174, align 8, !tbaa !3
  %v5175 = getelementptr i8, ptr %v5165, i64 96
  store ptr %v4758, ptr %v5175, align 8, !tbaa !3
  %v5176 = getelementptr i8, ptr %v5165, i64 104
  store ptr %v4760, ptr %v5176, align 8, !tbaa !3
  %v5177 = getelementptr i8, ptr %v5165, i64 112
  store ptr %v4762, ptr %v5177, align 8, !tbaa !3
  %v5178 = getelementptr i8, ptr %v5165, i64 120
  store ptr %v4764, ptr %v5178, align 8, !tbaa !3
  %v5179 = call ptr @mlf_closure(ptr @mlf.code.4817, ptr %v5165)
  %v5180 = call ptr @mlf_prim2(i64 1, ptr %v4816, ptr %v5179)
  ret ptr %v5180
}

define private ptr @mlf.code.4655(ptr %env, ptr %arg) {
entry:
  %v4656 = getelementptr i8, ptr %env, i64 24
  %v4657 = load ptr, ptr %v4656, align 8, !tbaa !3
  %v4658 = getelementptr i8, ptr %env, i64 32
  %v4659 = load ptr, ptr %v4658, align 8, !tbaa !3
  %v4660 = getelementptr i8, ptr %env, i64 40
  %v4661 = load ptr, ptr %v4660, align 8, !tbaa !3
  %v4662 = getelementptr i8, ptr %env, i64 48
  %v4663 = load ptr, ptr %v4662, align 8, !tbaa !3
  %v4664 = getelementptr i8, ptr %env, i64 56
  %v4665 = load ptr, ptr %v4664, align 8, !tbaa !3
  %v4666 = getelementptr i8, ptr %env, i64 64
  %v4667 = load ptr, ptr %v4666, align 8, !tbaa !3
  %v4668 = getelementptr i8, ptr %env, i64 72
  %v4669 = load ptr, ptr %v4668, align 8, !tbaa !3
  %v4670 = getelementptr i8, ptr %env, i64 80
  %v4671 = load ptr, ptr %v4670, align 8, !tbaa !3
  %v4672 = getelementptr i8, ptr %env, i64 88
  %v4673 = load ptr, ptr %v4672, align 8, !tbaa !3
  %v4674 = getelementptr i8, ptr %env, i64 96
  %v4675 = load ptr, ptr %v4674, align 8, !tbaa !3
  %v4676 = getelementptr i8, ptr %env, i64 104
  %v4677 = load ptr, ptr %v4676, align 8, !tbaa !3
  %v4678 = getelementptr i8, ptr %env, i64 112
  %v4679 = load ptr, ptr %v4678, align 8, !tbaa !3
  %v4680 = getelementptr i8, ptr %env, i64 120
  %v4681 = load ptr, ptr %v4680, align 8, !tbaa !3
  %v4682 = getelementptr i8, ptr %env, i64 128
  %v4683 = load ptr, ptr %v4682, align 8, !tbaa !3
  %v4728 = call ptr @mlf_env_new(i64 6)
  %v4729 = getelementptr i8, ptr %v4728, i64 24
  store ptr %v4657, ptr %v4729, align 8, !tbaa !3
  %v4730 = getelementptr i8, ptr %v4728, i64 32
  store ptr %v4659, ptr %v4730, align 8, !tbaa !3
  %v4731 = getelementptr i8, ptr %v4728, i64 40
  store ptr %v4665, ptr %v4731, align 8, !tbaa !3
  %v4732 = getelementptr i8, ptr %v4728, i64 48
  store ptr %v4667, ptr %v4732, align 8, !tbaa !3
  %v4733 = getelementptr i8, ptr %v4728, i64 56
  store ptr %v4673, ptr %v4733, align 8, !tbaa !3
  %v4734 = getelementptr i8, ptr %v4728, i64 64
  store ptr %v4675, ptr %v4734, align 8, !tbaa !3
  %v4735 = call ptr @mlf_thunk(ptr @mlf.code.4684, ptr %v4728)
  %v5181 = call ptr @mlf_env_new(i64 14)
  %v5182 = getelementptr i8, ptr %v5181, i64 24
  store ptr %v4657, ptr %v5182, align 8, !tbaa !3
  %v5183 = getelementptr i8, ptr %v5181, i64 32
  store ptr %v4659, ptr %v5183, align 8, !tbaa !3
  %v5184 = getelementptr i8, ptr %v5181, i64 40
  store ptr %v4661, ptr %v5184, align 8, !tbaa !3
  %v5185 = getelementptr i8, ptr %v5181, i64 48
  store ptr %v4663, ptr %v5185, align 8, !tbaa !3
  %v5186 = getelementptr i8, ptr %v5181, i64 56
  store ptr %v4665, ptr %v5186, align 8, !tbaa !3
  %v5187 = getelementptr i8, ptr %v5181, i64 64
  store ptr %v4667, ptr %v5187, align 8, !tbaa !3
  %v5188 = getelementptr i8, ptr %v5181, i64 72
  store ptr %v4669, ptr %v5188, align 8, !tbaa !3
  %v5189 = getelementptr i8, ptr %v5181, i64 80
  store ptr %v4671, ptr %v5189, align 8, !tbaa !3
  %v5190 = getelementptr i8, ptr %v5181, i64 88
  store ptr %v4673, ptr %v5190, align 8, !tbaa !3
  %v5191 = getelementptr i8, ptr %v5181, i64 96
  store ptr %v4677, ptr %v5191, align 8, !tbaa !3
  %v5192 = getelementptr i8, ptr %v5181, i64 104
  store ptr %v4679, ptr %v5192, align 8, !tbaa !3
  %v5193 = getelementptr i8, ptr %v5181, i64 112
  store ptr %v4681, ptr %v5193, align 8, !tbaa !3
  %v5194 = getelementptr i8, ptr %v5181, i64 120
  store ptr %v4683, ptr %v5194, align 8, !tbaa !3
  %v5195 = getelementptr i8, ptr %v5181, i64 128
  store ptr %arg, ptr %v5195, align 8, !tbaa !3
  %v5196 = call ptr @mlf_closure(ptr @mlf.code.4736, ptr %v5181)
  %v5197 = call ptr @mlf_prim2(i64 1, ptr %v4735, ptr %v5196)
  ret ptr %v5197
}

define private ptr @mlf.code.4610(ptr %env, ptr %arg) {
entry:
  %v4611 = getelementptr i8, ptr %env, i64 24
  %v4612 = load ptr, ptr %v4611, align 8, !tbaa !3
  %v4613 = getelementptr i8, ptr %env, i64 32
  %v4614 = load ptr, ptr %v4613, align 8, !tbaa !3
  %v4615 = getelementptr i8, ptr %env, i64 40
  %v4616 = load ptr, ptr %v4615, align 8, !tbaa !3
  %v4617 = getelementptr i8, ptr %env, i64 48
  %v4618 = load ptr, ptr %v4617, align 8, !tbaa !3
  %v4619 = getelementptr i8, ptr %env, i64 56
  %v4620 = load ptr, ptr %v4619, align 8, !tbaa !3
  %v4621 = getelementptr i8, ptr %env, i64 64
  %v4622 = load ptr, ptr %v4621, align 8, !tbaa !3
  %v4623 = getelementptr i8, ptr %env, i64 72
  %v4624 = load ptr, ptr %v4623, align 8, !tbaa !3
  %v4625 = getelementptr i8, ptr %env, i64 80
  %v4626 = load ptr, ptr %v4625, align 8, !tbaa !3
  %v4627 = getelementptr i8, ptr %env, i64 88
  %v4628 = load ptr, ptr %v4627, align 8, !tbaa !3
  %v4629 = getelementptr i8, ptr %env, i64 96
  %v4630 = load ptr, ptr %v4629, align 8, !tbaa !3
  %v4631 = getelementptr i8, ptr %env, i64 104
  %v4632 = load ptr, ptr %v4631, align 8, !tbaa !3
  %v4633 = getelementptr i8, ptr %env, i64 112
  %v4634 = load ptr, ptr %v4633, align 8, !tbaa !3
  %v4635 = getelementptr i8, ptr %env, i64 120
  %v4636 = load ptr, ptr %v4635, align 8, !tbaa !3
  %v4651 = call ptr @mlf_env_new(i64 2)
  %v4652 = getelementptr i8, ptr %v4651, i64 24
  store ptr %v4612, ptr %v4652, align 8, !tbaa !3
  %v4653 = getelementptr i8, ptr %v4651, i64 32
  store ptr %v4616, ptr %v4653, align 8, !tbaa !3
  %v4654 = call ptr @mlf_thunk(ptr @mlf.code.4637, ptr %v4651)
  %v5198 = call ptr @mlf_env_new(i64 14)
  %v5199 = getelementptr i8, ptr %v5198, i64 24
  store ptr %v4612, ptr %v5199, align 8, !tbaa !3
  %v5200 = getelementptr i8, ptr %v5198, i64 32
  store ptr %v4614, ptr %v5200, align 8, !tbaa !3
  %v5201 = getelementptr i8, ptr %v5198, i64 40
  store ptr %v4616, ptr %v5201, align 8, !tbaa !3
  %v5202 = getelementptr i8, ptr %v5198, i64 48
  store ptr %v4618, ptr %v5202, align 8, !tbaa !3
  %v5203 = getelementptr i8, ptr %v5198, i64 56
  store ptr %v4620, ptr %v5203, align 8, !tbaa !3
  %v5204 = getelementptr i8, ptr %v5198, i64 64
  store ptr %v4622, ptr %v5204, align 8, !tbaa !3
  %v5205 = getelementptr i8, ptr %v5198, i64 72
  store ptr %v4624, ptr %v5205, align 8, !tbaa !3
  %v5206 = getelementptr i8, ptr %v5198, i64 80
  store ptr %v4626, ptr %v5206, align 8, !tbaa !3
  %v5207 = getelementptr i8, ptr %v5198, i64 88
  store ptr %v4628, ptr %v5207, align 8, !tbaa !3
  %v5208 = getelementptr i8, ptr %v5198, i64 96
  store ptr %v4630, ptr %v5208, align 8, !tbaa !3
  %v5209 = getelementptr i8, ptr %v5198, i64 104
  store ptr %v4632, ptr %v5209, align 8, !tbaa !3
  %v5210 = getelementptr i8, ptr %v5198, i64 112
  store ptr %v4634, ptr %v5210, align 8, !tbaa !3
  %v5211 = getelementptr i8, ptr %v5198, i64 120
  store ptr %v4636, ptr %v5211, align 8, !tbaa !3
  %v5212 = getelementptr i8, ptr %v5198, i64 128
  store ptr %arg, ptr %v5212, align 8, !tbaa !3
  %v5213 = call ptr @mlf_closure(ptr @mlf.code.4655, ptr %v5198)
  %v5214 = call ptr @mlf_prim2(i64 1, ptr %v4654, ptr %v5213)
  ret ptr %v5214
}

define private ptr @mlf.code.4567(ptr %env, ptr %arg) {
entry:
  %v4568 = getelementptr i8, ptr %env, i64 24
  %v4569 = load ptr, ptr %v4568, align 8, !tbaa !3
  %v4570 = getelementptr i8, ptr %env, i64 32
  %v4571 = load ptr, ptr %v4570, align 8, !tbaa !3
  %v4572 = getelementptr i8, ptr %env, i64 40
  %v4573 = load ptr, ptr %v4572, align 8, !tbaa !3
  %v4574 = getelementptr i8, ptr %env, i64 48
  %v4575 = load ptr, ptr %v4574, align 8, !tbaa !3
  %v4576 = getelementptr i8, ptr %env, i64 56
  %v4577 = load ptr, ptr %v4576, align 8, !tbaa !3
  %v4578 = getelementptr i8, ptr %env, i64 64
  %v4579 = load ptr, ptr %v4578, align 8, !tbaa !3
  %v4580 = getelementptr i8, ptr %env, i64 72
  %v4581 = load ptr, ptr %v4580, align 8, !tbaa !3
  %v4582 = getelementptr i8, ptr %env, i64 80
  %v4583 = load ptr, ptr %v4582, align 8, !tbaa !3
  %v4584 = getelementptr i8, ptr %env, i64 88
  %v4585 = load ptr, ptr %v4584, align 8, !tbaa !3
  %v4586 = getelementptr i8, ptr %env, i64 96
  %v4587 = load ptr, ptr %v4586, align 8, !tbaa !3
  %v4588 = getelementptr i8, ptr %env, i64 104
  %v4589 = load ptr, ptr %v4588, align 8, !tbaa !3
  %v4590 = getelementptr i8, ptr %env, i64 112
  %v4591 = load ptr, ptr %v4590, align 8, !tbaa !3
  %v4606 = call ptr @mlf_env_new(i64 2)
  %v4607 = getelementptr i8, ptr %v4606, i64 24
  store ptr %v4569, ptr %v4607, align 8, !tbaa !3
  %v4608 = getelementptr i8, ptr %v4606, i64 32
  store ptr %v4573, ptr %v4608, align 8, !tbaa !3
  %v4609 = call ptr @mlf_thunk(ptr @mlf.code.4592, ptr %v4606)
  %v5215 = call ptr @mlf_env_new(i64 13)
  %v5216 = getelementptr i8, ptr %v5215, i64 24
  store ptr %v4569, ptr %v5216, align 8, !tbaa !3
  %v5217 = getelementptr i8, ptr %v5215, i64 32
  store ptr %v4571, ptr %v5217, align 8, !tbaa !3
  %v5218 = getelementptr i8, ptr %v5215, i64 40
  store ptr %v4573, ptr %v5218, align 8, !tbaa !3
  %v5219 = getelementptr i8, ptr %v5215, i64 48
  store ptr %v4575, ptr %v5219, align 8, !tbaa !3
  %v5220 = getelementptr i8, ptr %v5215, i64 56
  store ptr %v4577, ptr %v5220, align 8, !tbaa !3
  %v5221 = getelementptr i8, ptr %v5215, i64 64
  store ptr %v4579, ptr %v5221, align 8, !tbaa !3
  %v5222 = getelementptr i8, ptr %v5215, i64 72
  store ptr %v4581, ptr %v5222, align 8, !tbaa !3
  %v5223 = getelementptr i8, ptr %v5215, i64 80
  store ptr %v4583, ptr %v5223, align 8, !tbaa !3
  %v5224 = getelementptr i8, ptr %v5215, i64 88
  store ptr %v4585, ptr %v5224, align 8, !tbaa !3
  %v5225 = getelementptr i8, ptr %v5215, i64 96
  store ptr %v4587, ptr %v5225, align 8, !tbaa !3
  %v5226 = getelementptr i8, ptr %v5215, i64 104
  store ptr %v4589, ptr %v5226, align 8, !tbaa !3
  %v5227 = getelementptr i8, ptr %v5215, i64 112
  store ptr %v4591, ptr %v5227, align 8, !tbaa !3
  %v5228 = getelementptr i8, ptr %v5215, i64 120
  store ptr %arg, ptr %v5228, align 8, !tbaa !3
  %v5229 = call ptr @mlf_closure(ptr @mlf.code.4610, ptr %v5215)
  %v5230 = call ptr @mlf_prim2(i64 1, ptr %v4609, ptr %v5229)
  ret ptr %v5230
}

define private ptr @mlf.code.4526(ptr %env, ptr %arg) {
entry:
  %v4527 = getelementptr i8, ptr %env, i64 24
  %v4528 = load ptr, ptr %v4527, align 8, !tbaa !3
  %v4529 = getelementptr i8, ptr %env, i64 32
  %v4530 = load ptr, ptr %v4529, align 8, !tbaa !3
  %v4531 = getelementptr i8, ptr %env, i64 40
  %v4532 = load ptr, ptr %v4531, align 8, !tbaa !3
  %v4533 = getelementptr i8, ptr %env, i64 48
  %v4534 = load ptr, ptr %v4533, align 8, !tbaa !3
  %v4535 = getelementptr i8, ptr %env, i64 56
  %v4536 = load ptr, ptr %v4535, align 8, !tbaa !3
  %v4537 = getelementptr i8, ptr %env, i64 64
  %v4538 = load ptr, ptr %v4537, align 8, !tbaa !3
  %v4539 = getelementptr i8, ptr %env, i64 72
  %v4540 = load ptr, ptr %v4539, align 8, !tbaa !3
  %v4541 = getelementptr i8, ptr %env, i64 80
  %v4542 = load ptr, ptr %v4541, align 8, !tbaa !3
  %v4543 = getelementptr i8, ptr %env, i64 88
  %v4544 = load ptr, ptr %v4543, align 8, !tbaa !3
  %v4545 = getelementptr i8, ptr %env, i64 96
  %v4546 = load ptr, ptr %v4545, align 8, !tbaa !3
  %v4547 = getelementptr i8, ptr %env, i64 104
  %v4548 = load ptr, ptr %v4547, align 8, !tbaa !3
  %v4563 = call ptr @mlf_env_new(i64 2)
  %v4564 = getelementptr i8, ptr %v4563, i64 24
  store ptr %v4528, ptr %v4564, align 8, !tbaa !3
  %v4565 = getelementptr i8, ptr %v4563, i64 32
  store ptr %v4532, ptr %v4565, align 8, !tbaa !3
  %v4566 = call ptr @mlf_thunk(ptr @mlf.code.4549, ptr %v4563)
  %v5231 = call ptr @mlf_env_new(i64 12)
  %v5232 = getelementptr i8, ptr %v5231, i64 24
  store ptr %v4528, ptr %v5232, align 8, !tbaa !3
  %v5233 = getelementptr i8, ptr %v5231, i64 32
  store ptr %v4530, ptr %v5233, align 8, !tbaa !3
  %v5234 = getelementptr i8, ptr %v5231, i64 40
  store ptr %v4532, ptr %v5234, align 8, !tbaa !3
  %v5235 = getelementptr i8, ptr %v5231, i64 48
  store ptr %v4534, ptr %v5235, align 8, !tbaa !3
  %v5236 = getelementptr i8, ptr %v5231, i64 56
  store ptr %v4536, ptr %v5236, align 8, !tbaa !3
  %v5237 = getelementptr i8, ptr %v5231, i64 64
  store ptr %v4538, ptr %v5237, align 8, !tbaa !3
  %v5238 = getelementptr i8, ptr %v5231, i64 72
  store ptr %v4540, ptr %v5238, align 8, !tbaa !3
  %v5239 = getelementptr i8, ptr %v5231, i64 80
  store ptr %v4542, ptr %v5239, align 8, !tbaa !3
  %v5240 = getelementptr i8, ptr %v5231, i64 88
  store ptr %v4544, ptr %v5240, align 8, !tbaa !3
  %v5241 = getelementptr i8, ptr %v5231, i64 96
  store ptr %v4546, ptr %v5241, align 8, !tbaa !3
  %v5242 = getelementptr i8, ptr %v5231, i64 104
  store ptr %v4548, ptr %v5242, align 8, !tbaa !3
  %v5243 = getelementptr i8, ptr %v5231, i64 112
  store ptr %arg, ptr %v5243, align 8, !tbaa !3
  %v5244 = call ptr @mlf_closure(ptr @mlf.code.4567, ptr %v5231)
  %v5245 = call ptr @mlf_prim2(i64 1, ptr %v4566, ptr %v5244)
  ret ptr %v5245
}

define private ptr @mlf.code.4487(ptr %env, ptr %arg) {
entry:
  %v4488 = getelementptr i8, ptr %env, i64 24
  %v4489 = load ptr, ptr %v4488, align 8, !tbaa !3
  %v4490 = getelementptr i8, ptr %env, i64 32
  %v4491 = load ptr, ptr %v4490, align 8, !tbaa !3
  %v4492 = getelementptr i8, ptr %env, i64 40
  %v4493 = load ptr, ptr %v4492, align 8, !tbaa !3
  %v4494 = getelementptr i8, ptr %env, i64 48
  %v4495 = load ptr, ptr %v4494, align 8, !tbaa !3
  %v4496 = getelementptr i8, ptr %env, i64 56
  %v4497 = load ptr, ptr %v4496, align 8, !tbaa !3
  %v4498 = getelementptr i8, ptr %env, i64 64
  %v4499 = load ptr, ptr %v4498, align 8, !tbaa !3
  %v4500 = getelementptr i8, ptr %env, i64 72
  %v4501 = load ptr, ptr %v4500, align 8, !tbaa !3
  %v4502 = getelementptr i8, ptr %env, i64 80
  %v4503 = load ptr, ptr %v4502, align 8, !tbaa !3
  %v4504 = getelementptr i8, ptr %env, i64 88
  %v4505 = load ptr, ptr %v4504, align 8, !tbaa !3
  %v4506 = getelementptr i8, ptr %env, i64 96
  %v4507 = load ptr, ptr %v4506, align 8, !tbaa !3
  %v4522 = call ptr @mlf_env_new(i64 2)
  %v4523 = getelementptr i8, ptr %v4522, i64 24
  store ptr %v4489, ptr %v4523, align 8, !tbaa !3
  %v4524 = getelementptr i8, ptr %v4522, i64 32
  store ptr %v4491, ptr %v4524, align 8, !tbaa !3
  %v4525 = call ptr @mlf_thunk(ptr @mlf.code.4508, ptr %v4522)
  %v5246 = call ptr @mlf_env_new(i64 11)
  %v5247 = getelementptr i8, ptr %v5246, i64 24
  store ptr %v4489, ptr %v5247, align 8, !tbaa !3
  %v5248 = getelementptr i8, ptr %v5246, i64 32
  store ptr %v4491, ptr %v5248, align 8, !tbaa !3
  %v5249 = getelementptr i8, ptr %v5246, i64 40
  store ptr %v4493, ptr %v5249, align 8, !tbaa !3
  %v5250 = getelementptr i8, ptr %v5246, i64 48
  store ptr %v4495, ptr %v5250, align 8, !tbaa !3
  %v5251 = getelementptr i8, ptr %v5246, i64 56
  store ptr %v4497, ptr %v5251, align 8, !tbaa !3
  %v5252 = getelementptr i8, ptr %v5246, i64 64
  store ptr %v4499, ptr %v5252, align 8, !tbaa !3
  %v5253 = getelementptr i8, ptr %v5246, i64 72
  store ptr %v4501, ptr %v5253, align 8, !tbaa !3
  %v5254 = getelementptr i8, ptr %v5246, i64 80
  store ptr %v4503, ptr %v5254, align 8, !tbaa !3
  %v5255 = getelementptr i8, ptr %v5246, i64 88
  store ptr %v4505, ptr %v5255, align 8, !tbaa !3
  %v5256 = getelementptr i8, ptr %v5246, i64 96
  store ptr %v4507, ptr %v5256, align 8, !tbaa !3
  %v5257 = getelementptr i8, ptr %v5246, i64 104
  store ptr %arg, ptr %v5257, align 8, !tbaa !3
  %v5258 = call ptr @mlf_closure(ptr @mlf.code.4526, ptr %v5246)
  %v5259 = call ptr @mlf_prim2(i64 1, ptr %v4525, ptr %v5258)
  ret ptr %v5259
}

define private ptr @mlf.code.4450(ptr %env, ptr %arg) {
entry:
  %v4451 = getelementptr i8, ptr %env, i64 24
  %v4452 = load ptr, ptr %v4451, align 8, !tbaa !3
  %v4453 = getelementptr i8, ptr %env, i64 32
  %v4454 = load ptr, ptr %v4453, align 8, !tbaa !3
  %v4455 = getelementptr i8, ptr %env, i64 40
  %v4456 = load ptr, ptr %v4455, align 8, !tbaa !3
  %v4457 = getelementptr i8, ptr %env, i64 48
  %v4458 = load ptr, ptr %v4457, align 8, !tbaa !3
  %v4459 = getelementptr i8, ptr %env, i64 56
  %v4460 = load ptr, ptr %v4459, align 8, !tbaa !3
  %v4461 = getelementptr i8, ptr %env, i64 64
  %v4462 = load ptr, ptr %v4461, align 8, !tbaa !3
  %v4463 = getelementptr i8, ptr %env, i64 72
  %v4464 = load ptr, ptr %v4463, align 8, !tbaa !3
  %v4465 = getelementptr i8, ptr %env, i64 80
  %v4466 = load ptr, ptr %v4465, align 8, !tbaa !3
  %v4467 = getelementptr i8, ptr %env, i64 88
  %v4468 = load ptr, ptr %v4467, align 8, !tbaa !3
  %v4483 = call ptr @mlf_env_new(i64 2)
  %v4484 = getelementptr i8, ptr %v4483, i64 24
  store ptr %v4452, ptr %v4484, align 8, !tbaa !3
  %v4485 = getelementptr i8, ptr %v4483, i64 32
  store ptr %v4454, ptr %v4485, align 8, !tbaa !3
  %v4486 = call ptr @mlf_thunk(ptr @mlf.code.4469, ptr %v4483)
  %v5260 = call ptr @mlf_env_new(i64 10)
  %v5261 = getelementptr i8, ptr %v5260, i64 24
  store ptr %v4452, ptr %v5261, align 8, !tbaa !3
  %v5262 = getelementptr i8, ptr %v5260, i64 32
  store ptr %v4454, ptr %v5262, align 8, !tbaa !3
  %v5263 = getelementptr i8, ptr %v5260, i64 40
  store ptr %v4456, ptr %v5263, align 8, !tbaa !3
  %v5264 = getelementptr i8, ptr %v5260, i64 48
  store ptr %v4458, ptr %v5264, align 8, !tbaa !3
  %v5265 = getelementptr i8, ptr %v5260, i64 56
  store ptr %v4460, ptr %v5265, align 8, !tbaa !3
  %v5266 = getelementptr i8, ptr %v5260, i64 64
  store ptr %v4462, ptr %v5266, align 8, !tbaa !3
  %v5267 = getelementptr i8, ptr %v5260, i64 72
  store ptr %v4464, ptr %v5267, align 8, !tbaa !3
  %v5268 = getelementptr i8, ptr %v5260, i64 80
  store ptr %v4466, ptr %v5268, align 8, !tbaa !3
  %v5269 = getelementptr i8, ptr %v5260, i64 88
  store ptr %v4468, ptr %v5269, align 8, !tbaa !3
  %v5270 = getelementptr i8, ptr %v5260, i64 96
  store ptr %arg, ptr %v5270, align 8, !tbaa !3
  %v5271 = call ptr @mlf_closure(ptr @mlf.code.4487, ptr %v5260)
  %v5272 = call ptr @mlf_prim2(i64 1, ptr %v4486, ptr %v5271)
  ret ptr %v5272
}

define private ptr @mlf.code.4343(ptr %env, ptr %arg) {
entry:
  %v4344 = getelementptr i8, ptr %env, i64 24
  %v4345 = load ptr, ptr %v4344, align 8, !tbaa !3
  %v4346 = getelementptr i8, ptr %env, i64 32
  %v4347 = load ptr, ptr %v4346, align 8, !tbaa !3
  %v4348 = getelementptr i8, ptr %env, i64 40
  %v4349 = load ptr, ptr %v4348, align 8, !tbaa !3
  %v4350 = getelementptr i8, ptr %env, i64 48
  %v4351 = load ptr, ptr %v4350, align 8, !tbaa !3
  %v4352 = getelementptr i8, ptr %env, i64 56
  %v4353 = load ptr, ptr %v4352, align 8, !tbaa !3
  %v4354 = getelementptr i8, ptr %env, i64 64
  %v4355 = load ptr, ptr %v4354, align 8, !tbaa !3
  %v4356 = getelementptr i8, ptr %env, i64 72
  %v4357 = load ptr, ptr %v4356, align 8, !tbaa !3
  %v4358 = getelementptr i8, ptr %env, i64 80
  %v4359 = load ptr, ptr %v4358, align 8, !tbaa !3
  %v4360 = getelementptr i8, ptr %env, i64 88
  %v4361 = load ptr, ptr %v4360, align 8, !tbaa !3
  %v4362 = getelementptr i8, ptr %env, i64 96
  %v4363 = load ptr, ptr %v4362, align 8, !tbaa !3
  %v4372 = call ptr @mlf_env_new(i64 2)
  %v4373 = getelementptr i8, ptr %v4372, i64 24
  store ptr %v4351, ptr %v4373, align 8, !tbaa !3
  %v4374 = getelementptr i8, ptr %v4372, i64 32
  store ptr %v4359, ptr %v4374, align 8, !tbaa !3
  %v4375 = call ptr @mlf_thunk(ptr @mlf.code.4364, ptr %v4372)
  %v4384 = call ptr @mlf_env_new(i64 2)
  %v4385 = getelementptr i8, ptr %v4384, i64 24
  store ptr %v4353, ptr %v4385, align 8, !tbaa !3
  %v4386 = getelementptr i8, ptr %v4384, i64 32
  store ptr %v4361, ptr %v4386, align 8, !tbaa !3
  %v4387 = call ptr @mlf_thunk(ptr @mlf.code.4376, ptr %v4384)
  %v4396 = call ptr @mlf_env_new(i64 2)
  %v4397 = getelementptr i8, ptr %v4396, i64 24
  store ptr %v4355, ptr %v4397, align 8, !tbaa !3
  %v4398 = getelementptr i8, ptr %v4396, i64 32
  store ptr %v4363, ptr %v4398, align 8, !tbaa !3
  %v4399 = call ptr @mlf_thunk(ptr @mlf.code.4388, ptr %v4396)
  %v4416 = call ptr @mlf_env_new(i64 3)
  %v4417 = getelementptr i8, ptr %v4416, i64 24
  store ptr %v4375, ptr %v4417, align 8, !tbaa !3
  %v4418 = getelementptr i8, ptr %v4416, i64 32
  store ptr %v4387, ptr %v4418, align 8, !tbaa !3
  %v4419 = getelementptr i8, ptr %v4416, i64 40
  store ptr %v4399, ptr %v4419, align 8, !tbaa !3
  %v4420 = call ptr @mlf_thunk(ptr @mlf.code.4400, ptr %v4416)
  %v4429 = call ptr @mlf_env_new(i64 1)
  %v4430 = getelementptr i8, ptr %v4429, i64 24
  store ptr %v4420, ptr %v4430, align 8, !tbaa !3
  %v4431 = call ptr @mlf_thunk(ptr @mlf.code.4421, ptr %v4429)
  %v4446 = call ptr @mlf_env_new(i64 2)
  %v4447 = getelementptr i8, ptr %v4446, i64 24
  store ptr %v4345, ptr %v4447, align 8, !tbaa !3
  %v4448 = getelementptr i8, ptr %v4446, i64 32
  store ptr %v4347, ptr %v4448, align 8, !tbaa !3
  %v4449 = call ptr @mlf_thunk(ptr @mlf.code.4432, ptr %v4446)
  %v5273 = call ptr @mlf_env_new(i64 9)
  %v5274 = getelementptr i8, ptr %v5273, i64 24
  store ptr %v4345, ptr %v5274, align 8, !tbaa !3
  %v5275 = getelementptr i8, ptr %v5273, i64 32
  store ptr %v4347, ptr %v5275, align 8, !tbaa !3
  %v5276 = getelementptr i8, ptr %v5273, i64 40
  store ptr %v4349, ptr %v5276, align 8, !tbaa !3
  %v5277 = getelementptr i8, ptr %v5273, i64 48
  store ptr %v4357, ptr %v5277, align 8, !tbaa !3
  %v5278 = getelementptr i8, ptr %v5273, i64 56
  store ptr %arg, ptr %v5278, align 8, !tbaa !3
  %v5279 = getelementptr i8, ptr %v5273, i64 64
  store ptr %v4375, ptr %v5279, align 8, !tbaa !3
  %v5280 = getelementptr i8, ptr %v5273, i64 72
  store ptr %v4387, ptr %v5280, align 8, !tbaa !3
  %v5281 = getelementptr i8, ptr %v5273, i64 80
  store ptr %v4399, ptr %v5281, align 8, !tbaa !3
  %v5282 = getelementptr i8, ptr %v5273, i64 88
  store ptr %v4431, ptr %v5282, align 8, !tbaa !3
  %v5283 = call ptr @mlf_closure(ptr @mlf.code.4450, ptr %v5273)
  %v5284 = call ptr @mlf_prim2(i64 1, ptr %v4449, ptr %v5283)
  ret ptr %v5284
}

define private ptr @mlf.code.4306(ptr %env, ptr %arg) {
entry:
  %v4307 = getelementptr i8, ptr %env, i64 24
  %v4308 = load ptr, ptr %v4307, align 8, !tbaa !3
  %v4309 = getelementptr i8, ptr %env, i64 32
  %v4310 = load ptr, ptr %v4309, align 8, !tbaa !3
  %v4311 = getelementptr i8, ptr %env, i64 40
  %v4312 = load ptr, ptr %v4311, align 8, !tbaa !3
  %v4313 = getelementptr i8, ptr %env, i64 48
  %v4314 = load ptr, ptr %v4313, align 8, !tbaa !3
  %v4315 = getelementptr i8, ptr %env, i64 56
  %v4316 = load ptr, ptr %v4315, align 8, !tbaa !3
  %v4317 = getelementptr i8, ptr %env, i64 64
  %v4318 = load ptr, ptr %v4317, align 8, !tbaa !3
  %v4319 = getelementptr i8, ptr %env, i64 72
  %v4320 = load ptr, ptr %v4319, align 8, !tbaa !3
  %v4321 = getelementptr i8, ptr %env, i64 80
  %v4322 = load ptr, ptr %v4321, align 8, !tbaa !3
  %v4323 = getelementptr i8, ptr %env, i64 88
  %v4324 = load ptr, ptr %v4323, align 8, !tbaa !3
  %v4339 = call ptr @mlf_env_new(i64 2)
  %v4340 = getelementptr i8, ptr %v4339, i64 24
  store ptr %v4308, ptr %v4340, align 8, !tbaa !3
  %v4341 = getelementptr i8, ptr %v4339, i64 32
  store ptr %v4312, ptr %v4341, align 8, !tbaa !3
  %v4342 = call ptr @mlf_thunk(ptr @mlf.code.4325, ptr %v4339)
  %v5285 = call ptr @mlf_env_new(i64 10)
  %v5286 = getelementptr i8, ptr %v5285, i64 24
  store ptr %v4308, ptr %v5286, align 8, !tbaa !3
  %v5287 = getelementptr i8, ptr %v5285, i64 32
  store ptr %v4310, ptr %v5287, align 8, !tbaa !3
  %v5288 = getelementptr i8, ptr %v5285, i64 40
  store ptr %v4312, ptr %v5288, align 8, !tbaa !3
  %v5289 = getelementptr i8, ptr %v5285, i64 48
  store ptr %v4314, ptr %v5289, align 8, !tbaa !3
  %v5290 = getelementptr i8, ptr %v5285, i64 56
  store ptr %v4316, ptr %v5290, align 8, !tbaa !3
  %v5291 = getelementptr i8, ptr %v5285, i64 64
  store ptr %v4318, ptr %v5291, align 8, !tbaa !3
  %v5292 = getelementptr i8, ptr %v5285, i64 72
  store ptr %v4320, ptr %v5292, align 8, !tbaa !3
  %v5293 = getelementptr i8, ptr %v5285, i64 80
  store ptr %v4322, ptr %v5293, align 8, !tbaa !3
  %v5294 = getelementptr i8, ptr %v5285, i64 88
  store ptr %v4324, ptr %v5294, align 8, !tbaa !3
  %v5295 = getelementptr i8, ptr %v5285, i64 96
  store ptr %arg, ptr %v5295, align 8, !tbaa !3
  %v5296 = call ptr @mlf_closure(ptr @mlf.code.4343, ptr %v5285)
  %v5297 = call ptr @mlf_prim2(i64 1, ptr %v4342, ptr %v5296)
  ret ptr %v5297
}

define private ptr @mlf.code.4271(ptr %env, ptr %arg) {
entry:
  %v4272 = getelementptr i8, ptr %env, i64 24
  %v4273 = load ptr, ptr %v4272, align 8, !tbaa !3
  %v4274 = getelementptr i8, ptr %env, i64 32
  %v4275 = load ptr, ptr %v4274, align 8, !tbaa !3
  %v4276 = getelementptr i8, ptr %env, i64 40
  %v4277 = load ptr, ptr %v4276, align 8, !tbaa !3
  %v4278 = getelementptr i8, ptr %env, i64 48
  %v4279 = load ptr, ptr %v4278, align 8, !tbaa !3
  %v4280 = getelementptr i8, ptr %env, i64 56
  %v4281 = load ptr, ptr %v4280, align 8, !tbaa !3
  %v4282 = getelementptr i8, ptr %env, i64 64
  %v4283 = load ptr, ptr %v4282, align 8, !tbaa !3
  %v4284 = getelementptr i8, ptr %env, i64 72
  %v4285 = load ptr, ptr %v4284, align 8, !tbaa !3
  %v4286 = getelementptr i8, ptr %env, i64 80
  %v4287 = load ptr, ptr %v4286, align 8, !tbaa !3
  %v4302 = call ptr @mlf_env_new(i64 2)
  %v4303 = getelementptr i8, ptr %v4302, i64 24
  store ptr %v4273, ptr %v4303, align 8, !tbaa !3
  %v4304 = getelementptr i8, ptr %v4302, i64 32
  store ptr %v4277, ptr %v4304, align 8, !tbaa !3
  %v4305 = call ptr @mlf_thunk(ptr @mlf.code.4288, ptr %v4302)
  %v5298 = call ptr @mlf_env_new(i64 9)
  %v5299 = getelementptr i8, ptr %v5298, i64 24
  store ptr %v4273, ptr %v5299, align 8, !tbaa !3
  %v5300 = getelementptr i8, ptr %v5298, i64 32
  store ptr %v4275, ptr %v5300, align 8, !tbaa !3
  %v5301 = getelementptr i8, ptr %v5298, i64 40
  store ptr %v4277, ptr %v5301, align 8, !tbaa !3
  %v5302 = getelementptr i8, ptr %v5298, i64 48
  store ptr %v4279, ptr %v5302, align 8, !tbaa !3
  %v5303 = getelementptr i8, ptr %v5298, i64 56
  store ptr %v4281, ptr %v5303, align 8, !tbaa !3
  %v5304 = getelementptr i8, ptr %v5298, i64 64
  store ptr %v4283, ptr %v5304, align 8, !tbaa !3
  %v5305 = getelementptr i8, ptr %v5298, i64 72
  store ptr %v4285, ptr %v5305, align 8, !tbaa !3
  %v5306 = getelementptr i8, ptr %v5298, i64 80
  store ptr %v4287, ptr %v5306, align 8, !tbaa !3
  %v5307 = getelementptr i8, ptr %v5298, i64 88
  store ptr %arg, ptr %v5307, align 8, !tbaa !3
  %v5308 = call ptr @mlf_closure(ptr @mlf.code.4306, ptr %v5298)
  %v5309 = call ptr @mlf_prim2(i64 1, ptr %v4305, ptr %v5308)
  ret ptr %v5309
}

define private ptr @mlf.code.4238(ptr %env, ptr %arg) {
entry:
  %v4239 = getelementptr i8, ptr %env, i64 24
  %v4240 = load ptr, ptr %v4239, align 8, !tbaa !3
  %v4241 = getelementptr i8, ptr %env, i64 32
  %v4242 = load ptr, ptr %v4241, align 8, !tbaa !3
  %v4243 = getelementptr i8, ptr %env, i64 40
  %v4244 = load ptr, ptr %v4243, align 8, !tbaa !3
  %v4245 = getelementptr i8, ptr %env, i64 48
  %v4246 = load ptr, ptr %v4245, align 8, !tbaa !3
  %v4247 = getelementptr i8, ptr %env, i64 56
  %v4248 = load ptr, ptr %v4247, align 8, !tbaa !3
  %v4249 = getelementptr i8, ptr %env, i64 64
  %v4250 = load ptr, ptr %v4249, align 8, !tbaa !3
  %v4251 = getelementptr i8, ptr %env, i64 72
  %v4252 = load ptr, ptr %v4251, align 8, !tbaa !3
  %v4267 = call ptr @mlf_env_new(i64 2)
  %v4268 = getelementptr i8, ptr %v4267, i64 24
  store ptr %v4240, ptr %v4268, align 8, !tbaa !3
  %v4269 = getelementptr i8, ptr %v4267, i64 32
  store ptr %v4244, ptr %v4269, align 8, !tbaa !3
  %v4270 = call ptr @mlf_thunk(ptr @mlf.code.4253, ptr %v4267)
  %v5310 = call ptr @mlf_env_new(i64 8)
  %v5311 = getelementptr i8, ptr %v5310, i64 24
  store ptr %v4240, ptr %v5311, align 8, !tbaa !3
  %v5312 = getelementptr i8, ptr %v5310, i64 32
  store ptr %v4242, ptr %v5312, align 8, !tbaa !3
  %v5313 = getelementptr i8, ptr %v5310, i64 40
  store ptr %v4244, ptr %v5313, align 8, !tbaa !3
  %v5314 = getelementptr i8, ptr %v5310, i64 48
  store ptr %v4246, ptr %v5314, align 8, !tbaa !3
  %v5315 = getelementptr i8, ptr %v5310, i64 56
  store ptr %v4248, ptr %v5315, align 8, !tbaa !3
  %v5316 = getelementptr i8, ptr %v5310, i64 64
  store ptr %v4250, ptr %v5316, align 8, !tbaa !3
  %v5317 = getelementptr i8, ptr %v5310, i64 72
  store ptr %v4252, ptr %v5317, align 8, !tbaa !3
  %v5318 = getelementptr i8, ptr %v5310, i64 80
  store ptr %arg, ptr %v5318, align 8, !tbaa !3
  %v5319 = call ptr @mlf_closure(ptr @mlf.code.4271, ptr %v5310)
  %v5320 = call ptr @mlf_prim2(i64 1, ptr %v4270, ptr %v5319)
  ret ptr %v5320
}

define private ptr @mlf.code.4207(ptr %env, ptr %arg) {
entry:
  %v4208 = getelementptr i8, ptr %env, i64 24
  %v4209 = load ptr, ptr %v4208, align 8, !tbaa !3
  %v4210 = getelementptr i8, ptr %env, i64 32
  %v4211 = load ptr, ptr %v4210, align 8, !tbaa !3
  %v4212 = getelementptr i8, ptr %env, i64 40
  %v4213 = load ptr, ptr %v4212, align 8, !tbaa !3
  %v4214 = getelementptr i8, ptr %env, i64 48
  %v4215 = load ptr, ptr %v4214, align 8, !tbaa !3
  %v4216 = getelementptr i8, ptr %env, i64 56
  %v4217 = load ptr, ptr %v4216, align 8, !tbaa !3
  %v4218 = getelementptr i8, ptr %env, i64 64
  %v4219 = load ptr, ptr %v4218, align 8, !tbaa !3
  %v4234 = call ptr @mlf_env_new(i64 2)
  %v4235 = getelementptr i8, ptr %v4234, i64 24
  store ptr %v4209, ptr %v4235, align 8, !tbaa !3
  %v4236 = getelementptr i8, ptr %v4234, i64 32
  store ptr %v4213, ptr %v4236, align 8, !tbaa !3
  %v4237 = call ptr @mlf_thunk(ptr @mlf.code.4220, ptr %v4234)
  %v5321 = call ptr @mlf_env_new(i64 7)
  %v5322 = getelementptr i8, ptr %v5321, i64 24
  store ptr %v4209, ptr %v5322, align 8, !tbaa !3
  %v5323 = getelementptr i8, ptr %v5321, i64 32
  store ptr %v4211, ptr %v5323, align 8, !tbaa !3
  %v5324 = getelementptr i8, ptr %v5321, i64 40
  store ptr %v4213, ptr %v5324, align 8, !tbaa !3
  %v5325 = getelementptr i8, ptr %v5321, i64 48
  store ptr %v4215, ptr %v5325, align 8, !tbaa !3
  %v5326 = getelementptr i8, ptr %v5321, i64 56
  store ptr %v4217, ptr %v5326, align 8, !tbaa !3
  %v5327 = getelementptr i8, ptr %v5321, i64 64
  store ptr %v4219, ptr %v5327, align 8, !tbaa !3
  %v5328 = getelementptr i8, ptr %v5321, i64 72
  store ptr %arg, ptr %v5328, align 8, !tbaa !3
  %v5329 = call ptr @mlf_closure(ptr @mlf.code.4238, ptr %v5321)
  %v5330 = call ptr @mlf_prim2(i64 1, ptr %v4237, ptr %v5329)
  ret ptr %v5330
}

define private ptr @mlf.code.4178(ptr %env, ptr %arg) {
entry:
  %v4179 = getelementptr i8, ptr %env, i64 24
  %v4180 = load ptr, ptr %v4179, align 8, !tbaa !3
  %v4181 = getelementptr i8, ptr %env, i64 32
  %v4182 = load ptr, ptr %v4181, align 8, !tbaa !3
  %v4183 = getelementptr i8, ptr %env, i64 40
  %v4184 = load ptr, ptr %v4183, align 8, !tbaa !3
  %v4185 = getelementptr i8, ptr %env, i64 48
  %v4186 = load ptr, ptr %v4185, align 8, !tbaa !3
  %v4187 = getelementptr i8, ptr %env, i64 56
  %v4188 = load ptr, ptr %v4187, align 8, !tbaa !3
  %v4203 = call ptr @mlf_env_new(i64 2)
  %v4204 = getelementptr i8, ptr %v4203, i64 24
  store ptr %v4180, ptr %v4204, align 8, !tbaa !3
  %v4205 = getelementptr i8, ptr %v4203, i64 32
  store ptr %v4182, ptr %v4205, align 8, !tbaa !3
  %v4206 = call ptr @mlf_thunk(ptr @mlf.code.4189, ptr %v4203)
  %v5331 = call ptr @mlf_env_new(i64 6)
  %v5332 = getelementptr i8, ptr %v5331, i64 24
  store ptr %v4180, ptr %v5332, align 8, !tbaa !3
  %v5333 = getelementptr i8, ptr %v5331, i64 32
  store ptr %v4182, ptr %v5333, align 8, !tbaa !3
  %v5334 = getelementptr i8, ptr %v5331, i64 40
  store ptr %v4184, ptr %v5334, align 8, !tbaa !3
  %v5335 = getelementptr i8, ptr %v5331, i64 48
  store ptr %v4186, ptr %v5335, align 8, !tbaa !3
  %v5336 = getelementptr i8, ptr %v5331, i64 56
  store ptr %v4188, ptr %v5336, align 8, !tbaa !3
  %v5337 = getelementptr i8, ptr %v5331, i64 64
  store ptr %arg, ptr %v5337, align 8, !tbaa !3
  %v5338 = call ptr @mlf_closure(ptr @mlf.code.4207, ptr %v5331)
  %v5339 = call ptr @mlf_prim2(i64 1, ptr %v4206, ptr %v5338)
  ret ptr %v5339
}

define private ptr @mlf.code.4151(ptr %env, ptr %arg) {
entry:
  %v4152 = getelementptr i8, ptr %env, i64 24
  %v4153 = load ptr, ptr %v4152, align 8, !tbaa !3
  %v4154 = getelementptr i8, ptr %env, i64 32
  %v4155 = load ptr, ptr %v4154, align 8, !tbaa !3
  %v4156 = getelementptr i8, ptr %env, i64 40
  %v4157 = load ptr, ptr %v4156, align 8, !tbaa !3
  %v4158 = getelementptr i8, ptr %env, i64 48
  %v4159 = load ptr, ptr %v4158, align 8, !tbaa !3
  %v4174 = call ptr @mlf_env_new(i64 2)
  %v4175 = getelementptr i8, ptr %v4174, i64 24
  store ptr %v4153, ptr %v4175, align 8, !tbaa !3
  %v4176 = getelementptr i8, ptr %v4174, i64 32
  store ptr %v4155, ptr %v4176, align 8, !tbaa !3
  %v4177 = call ptr @mlf_thunk(ptr @mlf.code.4160, ptr %v4174)
  %v5340 = call ptr @mlf_env_new(i64 5)
  %v5341 = getelementptr i8, ptr %v5340, i64 24
  store ptr %v4153, ptr %v5341, align 8, !tbaa !3
  %v5342 = getelementptr i8, ptr %v5340, i64 32
  store ptr %v4155, ptr %v5342, align 8, !tbaa !3
  %v5343 = getelementptr i8, ptr %v5340, i64 40
  store ptr %v4157, ptr %v5343, align 8, !tbaa !3
  %v5344 = getelementptr i8, ptr %v5340, i64 48
  store ptr %v4159, ptr %v5344, align 8, !tbaa !3
  %v5345 = getelementptr i8, ptr %v5340, i64 56
  store ptr %arg, ptr %v5345, align 8, !tbaa !3
  %v5346 = call ptr @mlf_closure(ptr @mlf.code.4178, ptr %v5340)
  %v5347 = call ptr @mlf_prim2(i64 1, ptr %v4177, ptr %v5346)
  ret ptr %v5347
}

define private ptr @mlf.code.4126(ptr %env, ptr %arg) {
entry:
  %v4127 = getelementptr i8, ptr %env, i64 24
  %v4128 = load ptr, ptr %v4127, align 8, !tbaa !3
  %v4129 = getelementptr i8, ptr %env, i64 32
  %v4130 = load ptr, ptr %v4129, align 8, !tbaa !3
  %v4131 = getelementptr i8, ptr %env, i64 40
  %v4132 = load ptr, ptr %v4131, align 8, !tbaa !3
  %v4147 = call ptr @mlf_env_new(i64 2)
  %v4148 = getelementptr i8, ptr %v4147, i64 24
  store ptr %v4128, ptr %v4148, align 8, !tbaa !3
  %v4149 = getelementptr i8, ptr %v4147, i64 32
  store ptr %v4130, ptr %v4149, align 8, !tbaa !3
  %v4150 = call ptr @mlf_thunk(ptr @mlf.code.4133, ptr %v4147)
  %v5348 = call ptr @mlf_env_new(i64 4)
  %v5349 = getelementptr i8, ptr %v5348, i64 24
  store ptr %v4128, ptr %v5349, align 8, !tbaa !3
  %v5350 = getelementptr i8, ptr %v5348, i64 32
  store ptr %v4130, ptr %v5350, align 8, !tbaa !3
  %v5351 = getelementptr i8, ptr %v5348, i64 40
  store ptr %v4132, ptr %v5351, align 8, !tbaa !3
  %v5352 = getelementptr i8, ptr %v5348, i64 48
  store ptr %arg, ptr %v5352, align 8, !tbaa !3
  %v5353 = call ptr @mlf_closure(ptr @mlf.code.4151, ptr %v5348)
  %v5354 = call ptr @mlf_prim2(i64 1, ptr %v4150, ptr %v5353)
  ret ptr %v5354
}

define private ptr @mlf.worker.42(ptr %a0, ptr %a1, ptr %a2) {
entry:
  %v4102 = call ptr @mlf_prim2(i64 10, ptr %a2, ptr inttoptr (i64 71 to ptr))
  %v4103 = icmp eq ptr %v4102, inttoptr (i64 6 to ptr)
  br i1 %v4103, label %yes.4104, label %no.4105
yes.4104:
  %v4107 = call ptr @mlf_prim1(i64 0, ptr inttoptr (i64 4 to ptr))
  br label %join.4106
no.4105:
  %v4122 = call ptr @mlf_env_new(i64 2)
  %v4123 = getelementptr i8, ptr %v4122, i64 24
  store ptr %a0, ptr %v4123, align 8, !tbaa !3
  %v4124 = getelementptr i8, ptr %v4122, i64 32
  store ptr %a1, ptr %v4124, align 8, !tbaa !3
  %v4125 = call ptr @mlf_thunk(ptr @mlf.code.4108, ptr %v4122)
  %v5355 = call ptr @mlf_env_new(i64 3)
  %v5356 = getelementptr i8, ptr %v5355, i64 24
  store ptr %a0, ptr %v5356, align 8, !tbaa !3
  %v5357 = getelementptr i8, ptr %v5355, i64 32
  store ptr %a1, ptr %v5357, align 8, !tbaa !3
  %v5358 = getelementptr i8, ptr %v5355, i64 40
  store ptr %a2, ptr %v5358, align 8, !tbaa !3
  %v5359 = call ptr @mlf_closure(ptr @mlf.code.4126, ptr %v5355)
  %v5360 = call ptr @mlf_prim2(i64 1, ptr %v4125, ptr %v5359)
  br label %join.4106
join.4106:
  %v5361 = phi ptr [ %v4107, %yes.4104 ], [ %v5360, %no.4105 ]
  ret ptr %v5361
}

define private ptr @mlf.numeric.entry.4081(ptr %env, ptr %arg) {
entry:
  %v4082 = getelementptr i8, ptr %env, i64 24
  %v4083 = load ptr, ptr %v4082, align 8, !tbaa !3
  %v4084 = getelementptr i8, ptr %env, i64 32
  %v4085 = load ptr, ptr %v4084, align 8, !tbaa !3
  %v4086 = getelementptr i8, ptr %env, i64 40
  %v4087 = load ptr, ptr %v4086, align 8, !tbaa !3
  %v4088 = call ptr @mlf_peek(ptr %v4083)
  %v4089 = call ptr @mlf_peek(ptr %v4085)
  %v4090 = call ptr @mlf_peek(ptr %v4087)
  %v4091 = icmp ne ptr %v4088, null
  %v4092 = icmp ne ptr %v4089, null
  %v4093 = icmp ne ptr %v4090, null
  %v4094 = and i1 true, %v4091
  %v4095 = and i1 %v4094, %v4092
  %v4096 = and i1 %v4095, %v4093
  br i1 %v4096, label %yes.4097, label %no.4098
yes.4097:
  %v4100 = call ptr @mlf.numeric.42(ptr %v4088, ptr %v4089, ptr %v4090)
  %v4101 = call ptr @mlf_prim1(i64 0, ptr %v4100)
  br label %join.4099
no.4098:
  %v5362 = call ptr @mlf_force(ptr %v4087)
  %v5363 = call ptr @mlf.worker.42(ptr %v4083, ptr %v4085, ptr %v5362)
  br label %join.4099
join.4099:
  %v5364 = phi ptr [ %v4101, %yes.4097 ], [ %v5363, %no.4098 ]
  ret ptr %v5364
}

define private ptr @mlf.code.4076(ptr %env, ptr %arg) {
entry:
  %v4077 = getelementptr i8, ptr %env, i64 24
  %v4078 = load ptr, ptr %v4077, align 8, !tbaa !3
  %v4079 = getelementptr i8, ptr %env, i64 32
  %v4080 = load ptr, ptr %v4079, align 8, !tbaa !3
  %v5365 = call ptr @mlf_force(ptr %v4080)
  %v5366 = call ptr @mlf_prim2(i64 8, ptr %v5365, ptr inttoptr (i64 15 to ptr))
  %v5367 = call ptr @mlf_env_new(i64 3)
  %v5368 = getelementptr i8, ptr %v5367, i64 24
  store ptr %v4078, ptr %v5368, align 8, !tbaa !3
  %v5369 = getelementptr i8, ptr %v5367, i64 32
  store ptr %v4080, ptr %v5369, align 8, !tbaa !3
  %v5370 = getelementptr i8, ptr %v5367, i64 40
  store ptr %v5366, ptr %v5370, align 8, !tbaa !3
  %v5371 = call ptr @mlf_native_io(ptr @mlf.numeric.entry.4081, ptr %v5367)
  ret ptr %v5371
}

define private ptr @mlf.code.5376(ptr %env, ptr %arg) {
entry:
  %v5377 = getelementptr i8, ptr %env, i64 24
  %v5378 = load ptr, ptr %v5377, align 8, !tbaa !3
  %v5379 = getelementptr i8, ptr %env, i64 32
  %v5380 = load ptr, ptr %v5379, align 8, !tbaa !3
  %v5381 = call ptr @mlf_force(ptr %v5380)
  %v5382 = call ptr @mlf_prim2(i64 8, ptr %v5381, ptr inttoptr (i64 15 to ptr))
  %v5383 = call ptr @mlf_env_new(i64 2)
  %v5384 = getelementptr i8, ptr %v5383, i64 24
  store ptr %v5378, ptr %v5384, align 8, !tbaa !3
  %v5385 = getelementptr i8, ptr %v5383, i64 32
  store ptr %v5382, ptr %v5385, align 8, !tbaa !3
  %v5386 = call ptr @mlf_native_io(ptr @mlf.numeric.entry.4054, ptr %v5383)
  ret ptr %v5386
}

define private ptr @mlf.worker.77(ptr %a0, ptr %a1) {
entry:
  %v4070 = call ptr @mlf_prim2(i64 10, ptr %a1, ptr inttoptr (i64 71 to ptr))
  %v4071 = icmp eq ptr %v4070, inttoptr (i64 6 to ptr)
  br i1 %v4071, label %yes.4072, label %no.4073
yes.4072:
  %v4075 = call ptr @mlf_prim1(i64 0, ptr inttoptr (i64 4 to ptr))
  br label %join.4074
no.4073:
  %v5372 = call ptr @mlf_env_new(i64 2)
  %v5373 = getelementptr i8, ptr %v5372, i64 24
  store ptr %a0, ptr %v5373, align 8, !tbaa !3
  %v5374 = getelementptr i8, ptr %v5372, i64 32
  store ptr %a1, ptr %v5374, align 8, !tbaa !3
  %v5375 = call ptr @mlf_thunk(ptr @mlf.code.4076, ptr %v5372)
  %v5387 = call ptr @mlf_env_new(i64 2)
  %v5388 = getelementptr i8, ptr %v5387, i64 24
  store ptr %a0, ptr %v5388, align 8, !tbaa !3
  %v5389 = getelementptr i8, ptr %v5387, i64 32
  store ptr %a1, ptr %v5389, align 8, !tbaa !3
  %v5390 = call ptr @mlf_closure(ptr @mlf.code.5376, ptr %v5387)
  %v5391 = call ptr @mlf_prim2(i64 1, ptr %v5375, ptr %v5390)
  br label %join.4074
join.4074:
  %v5392 = phi ptr [ %v4075, %yes.4072 ], [ %v5391, %no.4073 ]
  ret ptr %v5392
}

define private ptr @mlf.numeric.entry.4054(ptr %env, ptr %arg) {
entry:
  %v4055 = getelementptr i8, ptr %env, i64 24
  %v4056 = load ptr, ptr %v4055, align 8, !tbaa !3
  %v4057 = getelementptr i8, ptr %env, i64 32
  %v4058 = load ptr, ptr %v4057, align 8, !tbaa !3
  %v4059 = call ptr @mlf_peek(ptr %v4056)
  %v4060 = call ptr @mlf_peek(ptr %v4058)
  %v4061 = icmp ne ptr %v4059, null
  %v4062 = icmp ne ptr %v4060, null
  %v4063 = and i1 true, %v4061
  %v4064 = and i1 %v4063, %v4062
  br i1 %v4064, label %yes.4065, label %no.4066
yes.4065:
  %v4068 = call ptr @mlf.numeric.77(ptr %v4059, ptr %v4060)
  %v4069 = call ptr @mlf_prim1(i64 0, ptr %v4068)
  br label %join.4067
no.4066:
  %v5393 = call ptr @mlf_force(ptr %v4058)
  %v5394 = call ptr @mlf.worker.77(ptr %v4056, ptr %v5393)
  br label %join.4067
join.4067:
  %v5395 = phi ptr [ %v4069, %yes.4065 ], [ %v5394, %no.4066 ]
  ret ptr %v5395
}

define private ptr @mlf.code.4051(ptr %env, ptr %arg) {
entry:
  %v4052 = getelementptr i8, ptr %env, i64 24
  %v4053 = load ptr, ptr %v4052, align 8, !tbaa !3
  %v5396 = call ptr @mlf_env_new(i64 2)
  %v5397 = getelementptr i8, ptr %v5396, i64 24
  store ptr %v4053, ptr %v5397, align 8, !tbaa !3
  %v5398 = getelementptr i8, ptr %v5396, i64 32
  store ptr inttoptr (i64 1 to ptr), ptr %v5398, align 8, !tbaa !3
  %v5399 = call ptr @mlf_native_io(ptr @mlf.numeric.entry.4054, ptr %v5396)
  ret ptr %v5399
}

define private ptr @mlf.code.5438(ptr %env, ptr %arg) {
entry:
  %v5439 = getelementptr i8, ptr %env, i64 24
  %v5440 = load ptr, ptr %v5439, align 8, !tbaa !3
  %v5441 = call ptr @mlf_force(ptr %v5440)
  %v5442 = call ptr @mlf_prim2(i64 8, ptr %v5441, ptr inttoptr (i64 1 to ptr))
  ret ptr %v5442
}

define private ptr @mlf.code.5433(ptr %env, ptr %arg) {
entry:
  %v5434 = getelementptr i8, ptr %env, i64 24
  %v5435 = load ptr, ptr %v5434, align 8, !tbaa !3
  %v5436 = getelementptr i8, ptr %env, i64 32
  %v5437 = load ptr, ptr %v5436, align 8, !tbaa !3
  %v5443 = call ptr @mlf_env_new(i64 1)
  %v5444 = getelementptr i8, ptr %v5443, i64 24
  store ptr %v5437, ptr %v5444, align 8, !tbaa !3
  %v5445 = call ptr @mlf_thunk(ptr @mlf.code.5438, ptr %v5443)
  %v5446 = call ptr @mlf_prim2(i64 32, ptr %v5435, ptr %v5445)
  ret ptr %v5446
}

define private ptr @mlf.code.5461(ptr %env, ptr %arg) {
entry:
  %v5462 = getelementptr i8, ptr %env, i64 24
  %v5463 = load ptr, ptr %v5462, align 8, !tbaa !3
  %v5464 = call ptr @mlf_force(ptr %v5463)
  %v5465 = call ptr @mlf_prim2(i64 8, ptr %v5464, ptr inttoptr (i64 3 to ptr))
  ret ptr %v5465
}

define private ptr @mlf.code.5456(ptr %env, ptr %arg) {
entry:
  %v5457 = getelementptr i8, ptr %env, i64 24
  %v5458 = load ptr, ptr %v5457, align 8, !tbaa !3
  %v5459 = getelementptr i8, ptr %env, i64 32
  %v5460 = load ptr, ptr %v5459, align 8, !tbaa !3
  %v5466 = call ptr @mlf_env_new(i64 1)
  %v5467 = getelementptr i8, ptr %v5466, i64 24
  store ptr %v5460, ptr %v5467, align 8, !tbaa !3
  %v5468 = call ptr @mlf_thunk(ptr @mlf.code.5461, ptr %v5466)
  %v5469 = call ptr @mlf_prim2(i64 32, ptr %v5458, ptr %v5468)
  ret ptr %v5469
}

define private ptr @mlf.code.5486(ptr %env, ptr %arg) {
entry:
  %v5487 = getelementptr i8, ptr %env, i64 24
  %v5488 = load ptr, ptr %v5487, align 8, !tbaa !3
  %v5489 = call ptr @mlf_force(ptr %v5488)
  %v5490 = call ptr @mlf_prim2(i64 8, ptr %v5489, ptr inttoptr (i64 5 to ptr))
  ret ptr %v5490
}

define private ptr @mlf.code.5481(ptr %env, ptr %arg) {
entry:
  %v5482 = getelementptr i8, ptr %env, i64 24
  %v5483 = load ptr, ptr %v5482, align 8, !tbaa !3
  %v5484 = getelementptr i8, ptr %env, i64 32
  %v5485 = load ptr, ptr %v5484, align 8, !tbaa !3
  %v5491 = call ptr @mlf_env_new(i64 1)
  %v5492 = getelementptr i8, ptr %v5491, i64 24
  store ptr %v5485, ptr %v5492, align 8, !tbaa !3
  %v5493 = call ptr @mlf_thunk(ptr @mlf.code.5486, ptr %v5491)
  %v5494 = call ptr @mlf_prim2(i64 32, ptr %v5483, ptr %v5493)
  ret ptr %v5494
}

define private ptr @mlf.code.5513(ptr %env, ptr %arg) {
entry:
  %v5514 = getelementptr i8, ptr %env, i64 24
  %v5515 = load ptr, ptr %v5514, align 8, !tbaa !3
  %v5516 = call ptr @mlf_force(ptr %v5515)
  %v5517 = call ptr @mlf_prim2(i64 8, ptr %v5516, ptr inttoptr (i64 7 to ptr))
  ret ptr %v5517
}

define private ptr @mlf.code.5508(ptr %env, ptr %arg) {
entry:
  %v5509 = getelementptr i8, ptr %env, i64 24
  %v5510 = load ptr, ptr %v5509, align 8, !tbaa !3
  %v5511 = getelementptr i8, ptr %env, i64 32
  %v5512 = load ptr, ptr %v5511, align 8, !tbaa !3
  %v5518 = call ptr @mlf_env_new(i64 1)
  %v5519 = getelementptr i8, ptr %v5518, i64 24
  store ptr %v5512, ptr %v5519, align 8, !tbaa !3
  %v5520 = call ptr @mlf_thunk(ptr @mlf.code.5513, ptr %v5518)
  %v5521 = call ptr @mlf_prim2(i64 32, ptr %v5510, ptr %v5520)
  ret ptr %v5521
}

define private ptr @mlf.code.5542(ptr %env, ptr %arg) {
entry:
  %v5543 = getelementptr i8, ptr %env, i64 24
  %v5544 = load ptr, ptr %v5543, align 8, !tbaa !3
  %v5545 = call ptr @mlf_force(ptr %v5544)
  %v5546 = call ptr @mlf_prim2(i64 8, ptr %v5545, ptr inttoptr (i64 9 to ptr))
  ret ptr %v5546
}

define private ptr @mlf.code.5537(ptr %env, ptr %arg) {
entry:
  %v5538 = getelementptr i8, ptr %env, i64 24
  %v5539 = load ptr, ptr %v5538, align 8, !tbaa !3
  %v5540 = getelementptr i8, ptr %env, i64 32
  %v5541 = load ptr, ptr %v5540, align 8, !tbaa !3
  %v5547 = call ptr @mlf_env_new(i64 1)
  %v5548 = getelementptr i8, ptr %v5547, i64 24
  store ptr %v5541, ptr %v5548, align 8, !tbaa !3
  %v5549 = call ptr @mlf_thunk(ptr @mlf.code.5542, ptr %v5547)
  %v5550 = call ptr @mlf_prim2(i64 32, ptr %v5539, ptr %v5549)
  ret ptr %v5550
}

define private ptr @mlf.code.5573(ptr %env, ptr %arg) {
entry:
  %v5574 = getelementptr i8, ptr %env, i64 24
  %v5575 = load ptr, ptr %v5574, align 8, !tbaa !3
  %v5576 = call ptr @mlf_force(ptr %v5575)
  %v5577 = call ptr @mlf_prim2(i64 8, ptr %v5576, ptr inttoptr (i64 11 to ptr))
  ret ptr %v5577
}

define private ptr @mlf.code.5568(ptr %env, ptr %arg) {
entry:
  %v5569 = getelementptr i8, ptr %env, i64 24
  %v5570 = load ptr, ptr %v5569, align 8, !tbaa !3
  %v5571 = getelementptr i8, ptr %env, i64 32
  %v5572 = load ptr, ptr %v5571, align 8, !tbaa !3
  %v5578 = call ptr @mlf_env_new(i64 1)
  %v5579 = getelementptr i8, ptr %v5578, i64 24
  store ptr %v5572, ptr %v5579, align 8, !tbaa !3
  %v5580 = call ptr @mlf_thunk(ptr @mlf.code.5573, ptr %v5578)
  %v5581 = call ptr @mlf_prim2(i64 32, ptr %v5570, ptr %v5580)
  ret ptr %v5581
}

define private ptr @mlf.code.5610(ptr %env, ptr %arg) {
entry:
  %v5611 = getelementptr i8, ptr %env, i64 24
  %v5612 = load ptr, ptr %v5611, align 8, !tbaa !3
  %v5613 = getelementptr i8, ptr %env, i64 32
  %v5614 = load ptr, ptr %v5613, align 8, !tbaa !3
  %v5615 = call ptr @mlf_force(ptr %v5612)
  %v5616 = call ptr @mlf_double(double 0x3f847ae147ae147b)
  %v5617 = call ptr @mlf_force(ptr %v5614)
  %v5618 = call ptr @mlf_prim2(i64 20, ptr %v5616, ptr %v5617)
  %v5619 = call ptr @mlf_prim2(i64 18, ptr %v5615, ptr %v5618)
  ret ptr %v5619
}

define private ptr @mlf.code.5624(ptr %env, ptr %arg) {
entry:
  %v5625 = getelementptr i8, ptr %env, i64 24
  %v5626 = load ptr, ptr %v5625, align 8, !tbaa !3
  %v5627 = call ptr @mlf_force(ptr %v5626)
  %v5628 = call ptr @mlf_prim2(i64 8, ptr %v5627, ptr inttoptr (i64 1 to ptr))
  ret ptr %v5628
}

define private ptr @mlf.code.5601(ptr %env, ptr %arg) {
entry:
  %v5602 = getelementptr i8, ptr %env, i64 24
  %v5603 = load ptr, ptr %v5602, align 8, !tbaa !3
  %v5604 = getelementptr i8, ptr %env, i64 32
  %v5605 = load ptr, ptr %v5604, align 8, !tbaa !3
  %v5606 = getelementptr i8, ptr %env, i64 40
  %v5607 = load ptr, ptr %v5606, align 8, !tbaa !3
  %v5608 = getelementptr i8, ptr %env, i64 48
  %v5609 = load ptr, ptr %v5608, align 8, !tbaa !3
  %v5620 = call ptr @mlf_env_new(i64 2)
  %v5621 = getelementptr i8, ptr %v5620, i64 24
  store ptr %v5607, ptr %v5621, align 8, !tbaa !3
  %v5622 = getelementptr i8, ptr %v5620, i64 32
  store ptr %v5609, ptr %v5622, align 8, !tbaa !3
  %v5623 = call ptr @mlf_thunk(ptr @mlf.code.5610, ptr %v5620)
  %v5629 = call ptr @mlf_env_new(i64 1)
  %v5630 = getelementptr i8, ptr %v5629, i64 24
  store ptr %v5605, ptr %v5630, align 8, !tbaa !3
  %v5631 = call ptr @mlf_thunk(ptr @mlf.code.5624, ptr %v5629)
  %v5632 = call ptr @mlf_prim3(i64 33, ptr %v5603, ptr %v5631, ptr %v5623)
  ret ptr %v5632
}

define private ptr @mlf.code.5661(ptr %env, ptr %arg) {
entry:
  %v5662 = getelementptr i8, ptr %env, i64 24
  %v5663 = load ptr, ptr %v5662, align 8, !tbaa !3
  %v5664 = getelementptr i8, ptr %env, i64 32
  %v5665 = load ptr, ptr %v5664, align 8, !tbaa !3
  %v5666 = call ptr @mlf_force(ptr %v5663)
  %v5667 = call ptr @mlf_double(double 0x3f847ae147ae147b)
  %v5668 = call ptr @mlf_force(ptr %v5665)
  %v5669 = call ptr @mlf_prim2(i64 20, ptr %v5667, ptr %v5668)
  %v5670 = call ptr @mlf_prim2(i64 18, ptr %v5666, ptr %v5669)
  ret ptr %v5670
}

define private ptr @mlf.code.5675(ptr %env, ptr %arg) {
entry:
  %v5676 = getelementptr i8, ptr %env, i64 24
  %v5677 = load ptr, ptr %v5676, align 8, !tbaa !3
  %v5678 = call ptr @mlf_force(ptr %v5677)
  %v5679 = call ptr @mlf_prim2(i64 8, ptr %v5678, ptr inttoptr (i64 3 to ptr))
  ret ptr %v5679
}

define private ptr @mlf.code.5652(ptr %env, ptr %arg) {
entry:
  %v5653 = getelementptr i8, ptr %env, i64 24
  %v5654 = load ptr, ptr %v5653, align 8, !tbaa !3
  %v5655 = getelementptr i8, ptr %env, i64 32
  %v5656 = load ptr, ptr %v5655, align 8, !tbaa !3
  %v5657 = getelementptr i8, ptr %env, i64 40
  %v5658 = load ptr, ptr %v5657, align 8, !tbaa !3
  %v5659 = getelementptr i8, ptr %env, i64 48
  %v5660 = load ptr, ptr %v5659, align 8, !tbaa !3
  %v5671 = call ptr @mlf_env_new(i64 2)
  %v5672 = getelementptr i8, ptr %v5671, i64 24
  store ptr %v5658, ptr %v5672, align 8, !tbaa !3
  %v5673 = getelementptr i8, ptr %v5671, i64 32
  store ptr %v5660, ptr %v5673, align 8, !tbaa !3
  %v5674 = call ptr @mlf_thunk(ptr @mlf.code.5661, ptr %v5671)
  %v5680 = call ptr @mlf_env_new(i64 1)
  %v5681 = getelementptr i8, ptr %v5680, i64 24
  store ptr %v5656, ptr %v5681, align 8, !tbaa !3
  %v5682 = call ptr @mlf_thunk(ptr @mlf.code.5675, ptr %v5680)
  %v5683 = call ptr @mlf_prim3(i64 33, ptr %v5654, ptr %v5682, ptr %v5674)
  ret ptr %v5683
}

define private ptr @mlf.code.5708(ptr %env, ptr %arg) {
entry:
  %v5709 = getelementptr i8, ptr %env, i64 24
  %v5710 = load ptr, ptr %v5709, align 8, !tbaa !3
  %v5711 = getelementptr i8, ptr %env, i64 32
  %v5712 = load ptr, ptr %v5711, align 8, !tbaa !3
  %v5713 = call ptr @mlf_force(ptr %v5710)
  %v5714 = call ptr @mlf_double(double 0x3f847ae147ae147b)
  %v5715 = call ptr @mlf_force(ptr %v5712)
  %v5716 = call ptr @mlf_prim2(i64 20, ptr %v5714, ptr %v5715)
  %v5717 = call ptr @mlf_prim2(i64 18, ptr %v5713, ptr %v5716)
  ret ptr %v5717
}

define private ptr @mlf.code.5722(ptr %env, ptr %arg) {
entry:
  %v5723 = getelementptr i8, ptr %env, i64 24
  %v5724 = load ptr, ptr %v5723, align 8, !tbaa !3
  %v5725 = call ptr @mlf_force(ptr %v5724)
  %v5726 = call ptr @mlf_prim2(i64 8, ptr %v5725, ptr inttoptr (i64 5 to ptr))
  ret ptr %v5726
}

define private ptr @mlf.code.5699(ptr %env, ptr %arg) {
entry:
  %v5700 = getelementptr i8, ptr %env, i64 24
  %v5701 = load ptr, ptr %v5700, align 8, !tbaa !3
  %v5702 = getelementptr i8, ptr %env, i64 32
  %v5703 = load ptr, ptr %v5702, align 8, !tbaa !3
  %v5704 = getelementptr i8, ptr %env, i64 40
  %v5705 = load ptr, ptr %v5704, align 8, !tbaa !3
  %v5706 = getelementptr i8, ptr %env, i64 48
  %v5707 = load ptr, ptr %v5706, align 8, !tbaa !3
  %v5718 = call ptr @mlf_env_new(i64 2)
  %v5719 = getelementptr i8, ptr %v5718, i64 24
  store ptr %v5705, ptr %v5719, align 8, !tbaa !3
  %v5720 = getelementptr i8, ptr %v5718, i64 32
  store ptr %v5707, ptr %v5720, align 8, !tbaa !3
  %v5721 = call ptr @mlf_thunk(ptr @mlf.code.5708, ptr %v5718)
  %v5727 = call ptr @mlf_env_new(i64 1)
  %v5728 = getelementptr i8, ptr %v5727, i64 24
  store ptr %v5703, ptr %v5728, align 8, !tbaa !3
  %v5729 = call ptr @mlf_thunk(ptr @mlf.code.5722, ptr %v5727)
  %v5730 = call ptr @mlf_prim3(i64 33, ptr %v5701, ptr %v5729, ptr %v5721)
  ret ptr %v5730
}

define private ptr @mlf.code.5737(ptr %env, ptr %arg) {
entry:
  %v5738 = getelementptr i8, ptr %env, i64 24
  %v5739 = load ptr, ptr %v5738, align 8, !tbaa !3
  %v5740 = getelementptr i8, ptr %env, i64 32
  %v5741 = load ptr, ptr %v5740, align 8, !tbaa !3
  %v5742 = call ptr @mlf_force(ptr %v5741)
  %v5743 = call ptr @mlf_prim2(i64 8, ptr %v5742, ptr inttoptr (i64 15 to ptr))
  %v5744 = call ptr @mlf_env_new(i64 2)
  %v5745 = getelementptr i8, ptr %v5744, i64 24
  store ptr %v5739, ptr %v5745, align 8, !tbaa !3
  %v5746 = getelementptr i8, ptr %v5744, i64 32
  store ptr %v5743, ptr %v5746, align 8, !tbaa !3
  %v5747 = call ptr @mlf_native_io(ptr @mlf.numeric.entry.5411, ptr %v5744)
  ret ptr %v5747
}

define private ptr @mlf.code.5690(ptr %env, ptr %arg) {
entry:
  %v5691 = getelementptr i8, ptr %env, i64 24
  %v5692 = load ptr, ptr %v5691, align 8, !tbaa !3
  %v5693 = getelementptr i8, ptr %env, i64 32
  %v5694 = load ptr, ptr %v5693, align 8, !tbaa !3
  %v5695 = getelementptr i8, ptr %env, i64 40
  %v5696 = load ptr, ptr %v5695, align 8, !tbaa !3
  %v5697 = getelementptr i8, ptr %env, i64 48
  %v5698 = load ptr, ptr %v5697, align 8, !tbaa !3
  %v5731 = call ptr @mlf_env_new(i64 4)
  %v5732 = getelementptr i8, ptr %v5731, i64 24
  store ptr %v5692, ptr %v5732, align 8, !tbaa !3
  %v5733 = getelementptr i8, ptr %v5731, i64 32
  store ptr %v5694, ptr %v5733, align 8, !tbaa !3
  %v5734 = getelementptr i8, ptr %v5731, i64 40
  store ptr %v5696, ptr %v5734, align 8, !tbaa !3
  %v5735 = getelementptr i8, ptr %v5731, i64 48
  store ptr %v5698, ptr %v5735, align 8, !tbaa !3
  %v5736 = call ptr @mlf_thunk(ptr @mlf.code.5699, ptr %v5731)
  %v5748 = call ptr @mlf_env_new(i64 2)
  %v5749 = getelementptr i8, ptr %v5748, i64 24
  store ptr %v5692, ptr %v5749, align 8, !tbaa !3
  %v5750 = getelementptr i8, ptr %v5748, i64 32
  store ptr %v5694, ptr %v5750, align 8, !tbaa !3
  %v5751 = call ptr @mlf_closure(ptr @mlf.code.5737, ptr %v5748)
  %v5752 = call ptr @mlf_prim2(i64 1, ptr %v5736, ptr %v5751)
  ret ptr %v5752
}

define private ptr @mlf.code.5639(ptr %env, ptr %arg) {
entry:
  %v5640 = getelementptr i8, ptr %env, i64 24
  %v5641 = load ptr, ptr %v5640, align 8, !tbaa !3
  %v5642 = getelementptr i8, ptr %env, i64 32
  %v5643 = load ptr, ptr %v5642, align 8, !tbaa !3
  %v5644 = getelementptr i8, ptr %env, i64 40
  %v5645 = load ptr, ptr %v5644, align 8, !tbaa !3
  %v5646 = getelementptr i8, ptr %env, i64 48
  %v5647 = load ptr, ptr %v5646, align 8, !tbaa !3
  %v5648 = getelementptr i8, ptr %env, i64 56
  %v5649 = load ptr, ptr %v5648, align 8, !tbaa !3
  %v5650 = getelementptr i8, ptr %env, i64 64
  %v5651 = load ptr, ptr %v5650, align 8, !tbaa !3
  %v5684 = call ptr @mlf_env_new(i64 4)
  %v5685 = getelementptr i8, ptr %v5684, i64 24
  store ptr %v5641, ptr %v5685, align 8, !tbaa !3
  %v5686 = getelementptr i8, ptr %v5684, i64 32
  store ptr %v5643, ptr %v5686, align 8, !tbaa !3
  %v5687 = getelementptr i8, ptr %v5684, i64 40
  store ptr %v5645, ptr %v5687, align 8, !tbaa !3
  %v5688 = getelementptr i8, ptr %v5684, i64 48
  store ptr %v5649, ptr %v5688, align 8, !tbaa !3
  %v5689 = call ptr @mlf_thunk(ptr @mlf.code.5652, ptr %v5684)
  %v5753 = call ptr @mlf_env_new(i64 4)
  %v5754 = getelementptr i8, ptr %v5753, i64 24
  store ptr %v5641, ptr %v5754, align 8, !tbaa !3
  %v5755 = getelementptr i8, ptr %v5753, i64 32
  store ptr %v5643, ptr %v5755, align 8, !tbaa !3
  %v5756 = getelementptr i8, ptr %v5753, i64 40
  store ptr %v5647, ptr %v5756, align 8, !tbaa !3
  %v5757 = getelementptr i8, ptr %v5753, i64 48
  store ptr %v5651, ptr %v5757, align 8, !tbaa !3
  %v5758 = call ptr @mlf_closure(ptr @mlf.code.5690, ptr %v5753)
  %v5759 = call ptr @mlf_prim2(i64 1, ptr %v5689, ptr %v5758)
  ret ptr %v5759
}

define private ptr @mlf.code.5586(ptr %env, ptr %arg) {
entry:
  %v5587 = getelementptr i8, ptr %env, i64 24
  %v5588 = load ptr, ptr %v5587, align 8, !tbaa !3
  %v5589 = getelementptr i8, ptr %env, i64 32
  %v5590 = load ptr, ptr %v5589, align 8, !tbaa !3
  %v5591 = getelementptr i8, ptr %env, i64 40
  %v5592 = load ptr, ptr %v5591, align 8, !tbaa !3
  %v5593 = getelementptr i8, ptr %env, i64 48
  %v5594 = load ptr, ptr %v5593, align 8, !tbaa !3
  %v5595 = getelementptr i8, ptr %env, i64 56
  %v5596 = load ptr, ptr %v5595, align 8, !tbaa !3
  %v5597 = getelementptr i8, ptr %env, i64 64
  %v5598 = load ptr, ptr %v5597, align 8, !tbaa !3
  %v5599 = getelementptr i8, ptr %env, i64 72
  %v5600 = load ptr, ptr %v5599, align 8, !tbaa !3
  %v5633 = call ptr @mlf_env_new(i64 4)
  %v5634 = getelementptr i8, ptr %v5633, i64 24
  store ptr %v5588, ptr %v5634, align 8, !tbaa !3
  %v5635 = getelementptr i8, ptr %v5633, i64 32
  store ptr %v5590, ptr %v5635, align 8, !tbaa !3
  %v5636 = getelementptr i8, ptr %v5633, i64 40
  store ptr %v5592, ptr %v5636, align 8, !tbaa !3
  %v5637 = getelementptr i8, ptr %v5633, i64 48
  store ptr %v5598, ptr %v5637, align 8, !tbaa !3
  %v5638 = call ptr @mlf_thunk(ptr @mlf.code.5601, ptr %v5633)
  %v5760 = call ptr @mlf_env_new(i64 6)
  %v5761 = getelementptr i8, ptr %v5760, i64 24
  store ptr %v5588, ptr %v5761, align 8, !tbaa !3
  %v5762 = getelementptr i8, ptr %v5760, i64 32
  store ptr %v5590, ptr %v5762, align 8, !tbaa !3
  %v5763 = getelementptr i8, ptr %v5760, i64 40
  store ptr %v5594, ptr %v5763, align 8, !tbaa !3
  %v5764 = getelementptr i8, ptr %v5760, i64 48
  store ptr %v5596, ptr %v5764, align 8, !tbaa !3
  %v5765 = getelementptr i8, ptr %v5760, i64 56
  store ptr %v5600, ptr %v5765, align 8, !tbaa !3
  %v5766 = getelementptr i8, ptr %v5760, i64 64
  store ptr %arg, ptr %v5766, align 8, !tbaa !3
  %v5767 = call ptr @mlf_closure(ptr @mlf.code.5639, ptr %v5760)
  %v5768 = call ptr @mlf_prim2(i64 1, ptr %v5638, ptr %v5767)
  ret ptr %v5768
}

define private ptr @mlf.code.5555(ptr %env, ptr %arg) {
entry:
  %v5556 = getelementptr i8, ptr %env, i64 24
  %v5557 = load ptr, ptr %v5556, align 8, !tbaa !3
  %v5558 = getelementptr i8, ptr %env, i64 32
  %v5559 = load ptr, ptr %v5558, align 8, !tbaa !3
  %v5560 = getelementptr i8, ptr %env, i64 40
  %v5561 = load ptr, ptr %v5560, align 8, !tbaa !3
  %v5562 = getelementptr i8, ptr %env, i64 48
  %v5563 = load ptr, ptr %v5562, align 8, !tbaa !3
  %v5564 = getelementptr i8, ptr %env, i64 56
  %v5565 = load ptr, ptr %v5564, align 8, !tbaa !3
  %v5566 = getelementptr i8, ptr %env, i64 64
  %v5567 = load ptr, ptr %v5566, align 8, !tbaa !3
  %v5582 = call ptr @mlf_env_new(i64 2)
  %v5583 = getelementptr i8, ptr %v5582, i64 24
  store ptr %v5557, ptr %v5583, align 8, !tbaa !3
  %v5584 = getelementptr i8, ptr %v5582, i64 32
  store ptr %v5559, ptr %v5584, align 8, !tbaa !3
  %v5585 = call ptr @mlf_thunk(ptr @mlf.code.5568, ptr %v5582)
  %v5769 = call ptr @mlf_env_new(i64 7)
  %v5770 = getelementptr i8, ptr %v5769, i64 24
  store ptr %v5557, ptr %v5770, align 8, !tbaa !3
  %v5771 = getelementptr i8, ptr %v5769, i64 32
  store ptr %v5559, ptr %v5771, align 8, !tbaa !3
  %v5772 = getelementptr i8, ptr %v5769, i64 40
  store ptr %v5561, ptr %v5772, align 8, !tbaa !3
  %v5773 = getelementptr i8, ptr %v5769, i64 48
  store ptr %v5563, ptr %v5773, align 8, !tbaa !3
  %v5774 = getelementptr i8, ptr %v5769, i64 56
  store ptr %v5565, ptr %v5774, align 8, !tbaa !3
  %v5775 = getelementptr i8, ptr %v5769, i64 64
  store ptr %v5567, ptr %v5775, align 8, !tbaa !3
  %v5776 = getelementptr i8, ptr %v5769, i64 72
  store ptr %arg, ptr %v5776, align 8, !tbaa !3
  %v5777 = call ptr @mlf_closure(ptr @mlf.code.5586, ptr %v5769)
  %v5778 = call ptr @mlf_prim2(i64 1, ptr %v5585, ptr %v5777)
  ret ptr %v5778
}

define private ptr @mlf.code.5526(ptr %env, ptr %arg) {
entry:
  %v5527 = getelementptr i8, ptr %env, i64 24
  %v5528 = load ptr, ptr %v5527, align 8, !tbaa !3
  %v5529 = getelementptr i8, ptr %env, i64 32
  %v5530 = load ptr, ptr %v5529, align 8, !tbaa !3
  %v5531 = getelementptr i8, ptr %env, i64 40
  %v5532 = load ptr, ptr %v5531, align 8, !tbaa !3
  %v5533 = getelementptr i8, ptr %env, i64 48
  %v5534 = load ptr, ptr %v5533, align 8, !tbaa !3
  %v5535 = getelementptr i8, ptr %env, i64 56
  %v5536 = load ptr, ptr %v5535, align 8, !tbaa !3
  %v5551 = call ptr @mlf_env_new(i64 2)
  %v5552 = getelementptr i8, ptr %v5551, i64 24
  store ptr %v5528, ptr %v5552, align 8, !tbaa !3
  %v5553 = getelementptr i8, ptr %v5551, i64 32
  store ptr %v5530, ptr %v5553, align 8, !tbaa !3
  %v5554 = call ptr @mlf_thunk(ptr @mlf.code.5537, ptr %v5551)
  %v5779 = call ptr @mlf_env_new(i64 6)
  %v5780 = getelementptr i8, ptr %v5779, i64 24
  store ptr %v5528, ptr %v5780, align 8, !tbaa !3
  %v5781 = getelementptr i8, ptr %v5779, i64 32
  store ptr %v5530, ptr %v5781, align 8, !tbaa !3
  %v5782 = getelementptr i8, ptr %v5779, i64 40
  store ptr %v5532, ptr %v5782, align 8, !tbaa !3
  %v5783 = getelementptr i8, ptr %v5779, i64 48
  store ptr %v5534, ptr %v5783, align 8, !tbaa !3
  %v5784 = getelementptr i8, ptr %v5779, i64 56
  store ptr %v5536, ptr %v5784, align 8, !tbaa !3
  %v5785 = getelementptr i8, ptr %v5779, i64 64
  store ptr %arg, ptr %v5785, align 8, !tbaa !3
  %v5786 = call ptr @mlf_closure(ptr @mlf.code.5555, ptr %v5779)
  %v5787 = call ptr @mlf_prim2(i64 1, ptr %v5554, ptr %v5786)
  ret ptr %v5787
}

define private ptr @mlf.code.5499(ptr %env, ptr %arg) {
entry:
  %v5500 = getelementptr i8, ptr %env, i64 24
  %v5501 = load ptr, ptr %v5500, align 8, !tbaa !3
  %v5502 = getelementptr i8, ptr %env, i64 32
  %v5503 = load ptr, ptr %v5502, align 8, !tbaa !3
  %v5504 = getelementptr i8, ptr %env, i64 40
  %v5505 = load ptr, ptr %v5504, align 8, !tbaa !3
  %v5506 = getelementptr i8, ptr %env, i64 48
  %v5507 = load ptr, ptr %v5506, align 8, !tbaa !3
  %v5522 = call ptr @mlf_env_new(i64 2)
  %v5523 = getelementptr i8, ptr %v5522, i64 24
  store ptr %v5501, ptr %v5523, align 8, !tbaa !3
  %v5524 = getelementptr i8, ptr %v5522, i64 32
  store ptr %v5503, ptr %v5524, align 8, !tbaa !3
  %v5525 = call ptr @mlf_thunk(ptr @mlf.code.5508, ptr %v5522)
  %v5788 = call ptr @mlf_env_new(i64 5)
  %v5789 = getelementptr i8, ptr %v5788, i64 24
  store ptr %v5501, ptr %v5789, align 8, !tbaa !3
  %v5790 = getelementptr i8, ptr %v5788, i64 32
  store ptr %v5503, ptr %v5790, align 8, !tbaa !3
  %v5791 = getelementptr i8, ptr %v5788, i64 40
  store ptr %v5505, ptr %v5791, align 8, !tbaa !3
  %v5792 = getelementptr i8, ptr %v5788, i64 48
  store ptr %v5507, ptr %v5792, align 8, !tbaa !3
  %v5793 = getelementptr i8, ptr %v5788, i64 56
  store ptr %arg, ptr %v5793, align 8, !tbaa !3
  %v5794 = call ptr @mlf_closure(ptr @mlf.code.5526, ptr %v5788)
  %v5795 = call ptr @mlf_prim2(i64 1, ptr %v5525, ptr %v5794)
  ret ptr %v5795
}

define private ptr @mlf.code.5474(ptr %env, ptr %arg) {
entry:
  %v5475 = getelementptr i8, ptr %env, i64 24
  %v5476 = load ptr, ptr %v5475, align 8, !tbaa !3
  %v5477 = getelementptr i8, ptr %env, i64 32
  %v5478 = load ptr, ptr %v5477, align 8, !tbaa !3
  %v5479 = getelementptr i8, ptr %env, i64 40
  %v5480 = load ptr, ptr %v5479, align 8, !tbaa !3
  %v5495 = call ptr @mlf_env_new(i64 2)
  %v5496 = getelementptr i8, ptr %v5495, i64 24
  store ptr %v5476, ptr %v5496, align 8, !tbaa !3
  %v5497 = getelementptr i8, ptr %v5495, i64 32
  store ptr %v5478, ptr %v5497, align 8, !tbaa !3
  %v5498 = call ptr @mlf_thunk(ptr @mlf.code.5481, ptr %v5495)
  %v5796 = call ptr @mlf_env_new(i64 4)
  %v5797 = getelementptr i8, ptr %v5796, i64 24
  store ptr %v5476, ptr %v5797, align 8, !tbaa !3
  %v5798 = getelementptr i8, ptr %v5796, i64 32
  store ptr %v5478, ptr %v5798, align 8, !tbaa !3
  %v5799 = getelementptr i8, ptr %v5796, i64 40
  store ptr %v5480, ptr %v5799, align 8, !tbaa !3
  %v5800 = getelementptr i8, ptr %v5796, i64 48
  store ptr %arg, ptr %v5800, align 8, !tbaa !3
  %v5801 = call ptr @mlf_closure(ptr @mlf.code.5499, ptr %v5796)
  %v5802 = call ptr @mlf_prim2(i64 1, ptr %v5498, ptr %v5801)
  ret ptr %v5802
}

define private ptr @mlf.code.5451(ptr %env, ptr %arg) {
entry:
  %v5452 = getelementptr i8, ptr %env, i64 24
  %v5453 = load ptr, ptr %v5452, align 8, !tbaa !3
  %v5454 = getelementptr i8, ptr %env, i64 32
  %v5455 = load ptr, ptr %v5454, align 8, !tbaa !3
  %v5470 = call ptr @mlf_env_new(i64 2)
  %v5471 = getelementptr i8, ptr %v5470, i64 24
  store ptr %v5453, ptr %v5471, align 8, !tbaa !3
  %v5472 = getelementptr i8, ptr %v5470, i64 32
  store ptr %v5455, ptr %v5472, align 8, !tbaa !3
  %v5473 = call ptr @mlf_thunk(ptr @mlf.code.5456, ptr %v5470)
  %v5803 = call ptr @mlf_env_new(i64 3)
  %v5804 = getelementptr i8, ptr %v5803, i64 24
  store ptr %v5453, ptr %v5804, align 8, !tbaa !3
  %v5805 = getelementptr i8, ptr %v5803, i64 32
  store ptr %v5455, ptr %v5805, align 8, !tbaa !3
  %v5806 = getelementptr i8, ptr %v5803, i64 40
  store ptr %arg, ptr %v5806, align 8, !tbaa !3
  %v5807 = call ptr @mlf_closure(ptr @mlf.code.5474, ptr %v5803)
  %v5808 = call ptr @mlf_prim2(i64 1, ptr %v5473, ptr %v5807)
  ret ptr %v5808
}

define private ptr @mlf.worker.81(ptr %a0, ptr %a1) {
entry:
  %v5427 = call ptr @mlf_prim2(i64 10, ptr %a1, ptr inttoptr (i64 71 to ptr))
  %v5428 = icmp eq ptr %v5427, inttoptr (i64 6 to ptr)
  br i1 %v5428, label %yes.5429, label %no.5430
yes.5429:
  %v5432 = call ptr @mlf_prim1(i64 0, ptr inttoptr (i64 4 to ptr))
  br label %join.5431
no.5430:
  %v5447 = call ptr @mlf_env_new(i64 2)
  %v5448 = getelementptr i8, ptr %v5447, i64 24
  store ptr %a0, ptr %v5448, align 8, !tbaa !3
  %v5449 = getelementptr i8, ptr %v5447, i64 32
  store ptr %a1, ptr %v5449, align 8, !tbaa !3
  %v5450 = call ptr @mlf_thunk(ptr @mlf.code.5433, ptr %v5447)
  %v5809 = call ptr @mlf_env_new(i64 2)
  %v5810 = getelementptr i8, ptr %v5809, i64 24
  store ptr %a0, ptr %v5810, align 8, !tbaa !3
  %v5811 = getelementptr i8, ptr %v5809, i64 32
  store ptr %a1, ptr %v5811, align 8, !tbaa !3
  %v5812 = call ptr @mlf_closure(ptr @mlf.code.5451, ptr %v5809)
  %v5813 = call ptr @mlf_prim2(i64 1, ptr %v5450, ptr %v5812)
  br label %join.5431
join.5431:
  %v5814 = phi ptr [ %v5432, %yes.5429 ], [ %v5813, %no.5430 ]
  ret ptr %v5814
}

define private ptr @mlf.numeric.entry.5411(ptr %env, ptr %arg) {
entry:
  %v5412 = getelementptr i8, ptr %env, i64 24
  %v5413 = load ptr, ptr %v5412, align 8, !tbaa !3
  %v5414 = getelementptr i8, ptr %env, i64 32
  %v5415 = load ptr, ptr %v5414, align 8, !tbaa !3
  %v5416 = call ptr @mlf_peek(ptr %v5413)
  %v5417 = call ptr @mlf_peek(ptr %v5415)
  %v5418 = icmp ne ptr %v5416, null
  %v5419 = icmp ne ptr %v5417, null
  %v5420 = and i1 true, %v5418
  %v5421 = and i1 %v5420, %v5419
  br i1 %v5421, label %yes.5422, label %no.5423
yes.5422:
  %v5425 = call ptr @mlf.numeric.81(ptr %v5416, ptr %v5417)
  %v5426 = call ptr @mlf_prim1(i64 0, ptr %v5425)
  br label %join.5424
no.5423:
  %v5815 = call ptr @mlf_force(ptr %v5415)
  %v5816 = call ptr @mlf.worker.81(ptr %v5413, ptr %v5815)
  br label %join.5424
join.5424:
  %v5817 = phi ptr [ %v5426, %yes.5422 ], [ %v5816, %no.5423 ]
  ret ptr %v5817
}

define private ptr @mlf.code.5408(ptr %env, ptr %arg) {
entry:
  %v5409 = getelementptr i8, ptr %env, i64 24
  %v5410 = load ptr, ptr %v5409, align 8, !tbaa !3
  %v5818 = call ptr @mlf_env_new(i64 2)
  %v5819 = getelementptr i8, ptr %v5818, i64 24
  store ptr %v5410, ptr %v5819, align 8, !tbaa !3
  %v5820 = getelementptr i8, ptr %v5818, i64 32
  store ptr inttoptr (i64 1 to ptr), ptr %v5820, align 8, !tbaa !3
  %v5821 = call ptr @mlf_native_io(ptr @mlf.numeric.entry.5411, ptr %v5818)
  ret ptr %v5821
}

define private ptr @mlf.code.5825(ptr %env, ptr %arg) {
entry:
  %v5826 = getelementptr i8, ptr %env, i64 24
  %v5827 = load ptr, ptr %v5826, align 8, !tbaa !3
  %v5828 = getelementptr i8, ptr %env, i64 32
  %v5829 = load ptr, ptr %v5828, align 8, !tbaa !3
  %v5830 = call ptr @mlf_force(ptr %v5829)
  %v5831 = call ptr @mlf_prim2(i64 9, ptr %v5830, ptr inttoptr (i64 3 to ptr))
  %v5832 = call ptr @mlf_env_new(i64 2)
  %v5833 = getelementptr i8, ptr %v5832, i64 24
  store ptr %v5827, ptr %v5833, align 8, !tbaa !3
  %v5834 = getelementptr i8, ptr %v5832, i64 32
  store ptr %v5831, ptr %v5834, align 8, !tbaa !3
  %v5835 = call ptr @mlf_native_io(ptr @mlf.numeric.entry.3442, ptr %v5832)
  ret ptr %v5835
}

define private ptr @mlf.code.5403(ptr %env, ptr %arg) {
entry:
  %v5404 = getelementptr i8, ptr %env, i64 24
  %v5405 = load ptr, ptr %v5404, align 8, !tbaa !3
  %v5406 = getelementptr i8, ptr %env, i64 32
  %v5407 = load ptr, ptr %v5406, align 8, !tbaa !3
  %v5822 = call ptr @mlf_env_new(i64 1)
  %v5823 = getelementptr i8, ptr %v5822, i64 24
  store ptr %v5405, ptr %v5823, align 8, !tbaa !3
  %v5824 = call ptr @mlf_thunk(ptr @mlf.code.5408, ptr %v5822)
  %v5836 = call ptr @mlf_env_new(i64 2)
  %v5837 = getelementptr i8, ptr %v5836, i64 24
  store ptr %v5405, ptr %v5837, align 8, !tbaa !3
  %v5838 = getelementptr i8, ptr %v5836, i64 32
  store ptr %v5407, ptr %v5838, align 8, !tbaa !3
  %v5839 = call ptr @mlf_closure(ptr @mlf.code.5825, ptr %v5836)
  %v5840 = call ptr @mlf_prim2(i64 1, ptr %v5824, ptr %v5839)
  ret ptr %v5840
}

define private ptr @mlf.worker.96(ptr %a0, ptr %a1) {
entry:
  %v4045 = call ptr @mlf_prim2(i64 10, ptr %a1, ptr inttoptr (i64 1 to ptr))
  %v4046 = icmp eq ptr %v4045, inttoptr (i64 6 to ptr)
  br i1 %v4046, label %yes.4047, label %no.4048
yes.4047:
  %v4050 = call ptr @mlf_prim1(i64 0, ptr inttoptr (i64 4 to ptr))
  br label %join.4049
no.4048:
  %v5400 = call ptr @mlf_env_new(i64 1)
  %v5401 = getelementptr i8, ptr %v5400, i64 24
  store ptr %a0, ptr %v5401, align 8, !tbaa !3
  %v5402 = call ptr @mlf_thunk(ptr @mlf.code.4051, ptr %v5400)
  %v5841 = call ptr @mlf_env_new(i64 2)
  %v5842 = getelementptr i8, ptr %v5841, i64 24
  store ptr %a0, ptr %v5842, align 8, !tbaa !3
  %v5843 = getelementptr i8, ptr %v5841, i64 32
  store ptr %a1, ptr %v5843, align 8, !tbaa !3
  %v5844 = call ptr @mlf_closure(ptr @mlf.code.5403, ptr %v5841)
  %v5845 = call ptr @mlf_prim2(i64 1, ptr %v5402, ptr %v5844)
  br label %join.4049
join.4049:
  %v5846 = phi ptr [ %v4050, %yes.4047 ], [ %v5845, %no.4048 ]
  ret ptr %v5846
}

define private ptr @mlf.numeric.entry.3442(ptr %env, ptr %arg) {
entry:
  %v3443 = getelementptr i8, ptr %env, i64 24
  %v3444 = load ptr, ptr %v3443, align 8, !tbaa !3
  %v3445 = getelementptr i8, ptr %env, i64 32
  %v3446 = load ptr, ptr %v3445, align 8, !tbaa !3
  %v3447 = call ptr @mlf_peek(ptr %v3444)
  %v3448 = call ptr @mlf_peek(ptr %v3446)
  %v3449 = icmp ne ptr %v3447, null
  %v3450 = icmp ne ptr %v3448, null
  %v3451 = and i1 true, %v3449
  %v3452 = and i1 %v3451, %v3450
  br i1 %v3452, label %yes.3453, label %no.3454
yes.3453:
  %v4043 = call ptr @mlf.numeric.96(ptr %v3447, ptr %v3448)
  %v4044 = call ptr @mlf_prim1(i64 0, ptr %v4043)
  br label %join.3455
no.3454:
  %v5847 = call ptr @mlf_force(ptr %v3446)
  %v5848 = call ptr @mlf.worker.96(ptr %v3444, ptr %v5847)
  br label %join.3455
join.3455:
  %v5849 = phi ptr [ %v4044, %yes.3453 ], [ %v5848, %no.3454 ]
  ret ptr %v5849
}

define private ptr @mlf.code.3437(ptr %env, ptr %arg) {
entry:
  %v3438 = getelementptr i8, ptr %env, i64 24
  %v3439 = load ptr, ptr %v3438, align 8, !tbaa !3
  %v3440 = getelementptr i8, ptr %env, i64 32
  %v3441 = load ptr, ptr %v3440, align 8, !tbaa !3
  %v5850 = call ptr @mlf_force(ptr %v3439)
  %v5851 = call ptr @mlf_prim1(i64 17, ptr %v5850)
  %v5852 = call ptr @mlf_env_new(i64 2)
  %v5853 = getelementptr i8, ptr %v5852, i64 24
  store ptr %v3441, ptr %v5853, align 8, !tbaa !3
  %v5854 = getelementptr i8, ptr %v5852, i64 32
  store ptr %v5851, ptr %v5854, align 8, !tbaa !3
  %v5855 = call ptr @mlf_native_io(ptr @mlf.numeric.entry.3442, ptr %v5852)
  ret ptr %v5855
}

define private ptr @mlf.code.5863(ptr %env, ptr %arg) {
entry:
  %v5864 = getelementptr i8, ptr %env, i64 24
  %v5865 = load ptr, ptr %v5864, align 8, !tbaa !3
  %v5866 = call ptr @mlf_double(double 0x0000000000000000)
  %v5867 = call ptr @mlf_env_new(i64 3)
  %v5868 = getelementptr i8, ptr %v5867, i64 24
  store ptr %v5865, ptr %v5868, align 8, !tbaa !3
  %v5869 = getelementptr i8, ptr %v5867, i64 32
  store ptr inttoptr (i64 1 to ptr), ptr %v5869, align 8, !tbaa !3
  %v5870 = getelementptr i8, ptr %v5867, i64 40
  store ptr %v5866, ptr %v5870, align 8, !tbaa !3
  %v5871 = call ptr @mlf_native_io(ptr @mlf.numeric.entry.2203, ptr %v5867)
  ret ptr %v5871
}

define private ptr @mlf.code.5876(ptr %env, ptr %arg) {
entry:
  %v5877 = getelementptr i8, ptr %env, i64 24
  %v5878 = load ptr, ptr %v5877, align 8, !tbaa !3
  %v5879 = call ptr @mlf_force(ptr %v5878)
  %v5880 = call ptr @mlf_prim2(i64 26, ptr inttoptr (i64 19 to ptr), ptr %v5879)
  ret ptr %v5880
}

define private ptr @mlf.code.5875(ptr %env, ptr %arg) {
entry:
  %v5881 = call ptr @mlf_env_new(i64 1)
  %v5882 = getelementptr i8, ptr %v5881, i64 24
  store ptr %arg, ptr %v5882, align 8, !tbaa !3
  %v5883 = call ptr @mlf_thunk(ptr @mlf.code.5876, ptr %v5881)
  %v5884 = call ptr @mlf_prim1(i64 3, ptr %v5883)
  ret ptr %v5884
}

define private ptr @mlf.code.5860(ptr %env, ptr %arg) {
entry:
  %v5861 = getelementptr i8, ptr %env, i64 24
  %v5862 = load ptr, ptr %v5861, align 8, !tbaa !3
  %v5872 = call ptr @mlf_env_new(i64 1)
  %v5873 = getelementptr i8, ptr %v5872, i64 24
  store ptr %v5862, ptr %v5873, align 8, !tbaa !3
  %v5874 = call ptr @mlf_thunk(ptr @mlf.code.5863, ptr %v5872)
  %v5885 = call ptr @mlf_closure(ptr @mlf.code.5875, ptr null)
  %v5886 = call ptr @mlf_prim2(i64 1, ptr %v5874, ptr %v5885)
  ret ptr %v5886
}

define private ptr @mlf.code.3432(ptr %env, ptr %arg) {
entry:
  %v3433 = getelementptr i8, ptr %env, i64 24
  %v3434 = load ptr, ptr %v3433, align 8, !tbaa !3
  %v3435 = getelementptr i8, ptr %env, i64 32
  %v3436 = load ptr, ptr %v3435, align 8, !tbaa !3
  %v5856 = call ptr @mlf_env_new(i64 2)
  %v5857 = getelementptr i8, ptr %v5856, i64 24
  store ptr %v3434, ptr %v5857, align 8, !tbaa !3
  %v5858 = getelementptr i8, ptr %v5856, i64 32
  store ptr %v3436, ptr %v5858, align 8, !tbaa !3
  %v5859 = call ptr @mlf_thunk(ptr @mlf.code.3437, ptr %v5856)
  %v5887 = call ptr @mlf_env_new(i64 1)
  %v5888 = getelementptr i8, ptr %v5887, i64 24
  store ptr %v3436, ptr %v5888, align 8, !tbaa !3
  %v5889 = call ptr @mlf_closure(ptr @mlf.code.5860, ptr %v5887)
  %v5890 = call ptr @mlf_prim2(i64 1, ptr %v5859, ptr %v5889)
  ret ptr %v5890
}

define private ptr @mlf.code.3412(ptr %env, ptr %arg) {
entry:
  %v3413 = getelementptr i8, ptr %env, i64 24
  %v3414 = load ptr, ptr %v3413, align 8, !tbaa !3
  %v3415 = getelementptr i8, ptr %env, i64 32
  %v3416 = load ptr, ptr %v3415, align 8, !tbaa !3
  %v3429 = call ptr @mlf_env_new(i64 1)
  %v3430 = getelementptr i8, ptr %v3429, i64 24
  store ptr %arg, ptr %v3430, align 8, !tbaa !3
  %v3431 = call ptr @mlf_thunk(ptr @mlf.code.3417, ptr %v3429)
  %v5891 = call ptr @mlf_env_new(i64 2)
  %v5892 = getelementptr i8, ptr %v5891, i64 24
  store ptr %v3414, ptr %v5892, align 8, !tbaa !3
  %v5893 = getelementptr i8, ptr %v5891, i64 32
  store ptr %v3416, ptr %v5893, align 8, !tbaa !3
  %v5894 = call ptr @mlf_closure(ptr @mlf.code.3432, ptr %v5891)
  %v5895 = call ptr @mlf_prim2(i64 1, ptr %v3431, ptr %v5894)
  ret ptr %v5895
}

define private ptr @mlf.code.2195(ptr %env, ptr %arg) {
entry:
  %v2196 = getelementptr i8, ptr %env, i64 24
  %v2197 = load ptr, ptr %v2196, align 8, !tbaa !3
  %v2198 = getelementptr i8, ptr %env, i64 32
  %v2199 = load ptr, ptr %v2198, align 8, !tbaa !3
  %v3409 = call ptr @mlf_env_new(i64 1)
  %v3410 = getelementptr i8, ptr %v3409, i64 24
  store ptr %v2199, ptr %v3410, align 8, !tbaa !3
  %v3411 = call ptr @mlf_thunk(ptr @mlf.code.2200, ptr %v3409)
  %v5896 = call ptr @mlf_env_new(i64 2)
  %v5897 = getelementptr i8, ptr %v5896, i64 24
  store ptr %v2197, ptr %v5897, align 8, !tbaa !3
  %v5898 = getelementptr i8, ptr %v5896, i64 32
  store ptr %v2199, ptr %v5898, align 8, !tbaa !3
  %v5899 = call ptr @mlf_closure(ptr @mlf.code.3412, ptr %v5896)
  %v5900 = call ptr @mlf_prim2(i64 1, ptr %v3411, ptr %v5899)
  ret ptr %v5900
}

define private ptr @mlf.code.1355(ptr %env, ptr %arg) {
entry:
  %v1356 = getelementptr i8, ptr %env, i64 24
  %v1357 = load ptr, ptr %v1356, align 8, !tbaa !3
  %v1358 = getelementptr i8, ptr %env, i64 32
  %v1359 = load ptr, ptr %v1358, align 8, !tbaa !3
  %v1360 = getelementptr i8, ptr %env, i64 40
  %v1361 = load ptr, ptr %v1360, align 8, !tbaa !3
  %v2191 = call ptr @mlf_env_new(i64 2)
  %v2192 = getelementptr i8, ptr %v2191, i64 24
  store ptr %v1357, ptr %v2192, align 8, !tbaa !3
  %v2193 = getelementptr i8, ptr %v2191, i64 32
  store ptr %v1361, ptr %v2193, align 8, !tbaa !3
  %v2194 = call ptr @mlf_thunk(ptr @mlf.code.1362, ptr %v2191)
  %v5901 = call ptr @mlf_env_new(i64 2)
  %v5902 = getelementptr i8, ptr %v5901, i64 24
  store ptr %v1359, ptr %v5902, align 8, !tbaa !3
  %v5903 = getelementptr i8, ptr %v5901, i64 32
  store ptr %v1361, ptr %v5903, align 8, !tbaa !3
  %v5904 = call ptr @mlf_closure(ptr @mlf.code.2195, ptr %v5901)
  %v5905 = call ptr @mlf_prim2(i64 1, ptr %v2194, ptr %v5904)
  ret ptr %v5905
}

define private ptr @mlf.code.26(ptr %env, ptr %arg) {
entry:
  %v27 = getelementptr i8, ptr %env, i64 24
  %v28 = load ptr, ptr %v27, align 8, !tbaa !3
  %v29 = getelementptr i8, ptr %env, i64 32
  %v30 = load ptr, ptr %v29, align 8, !tbaa !3
  %v1351 = call ptr @mlf_env_new(i64 2)
  %v1352 = getelementptr i8, ptr %v1351, i64 24
  store ptr %v28, ptr %v1352, align 8, !tbaa !3
  %v1353 = getelementptr i8, ptr %v1351, i64 32
  store ptr %arg, ptr %v1353, align 8, !tbaa !3
  %v1354 = call ptr @mlf_thunk(ptr @mlf.code.31, ptr %v1351)
  %v5906 = call ptr @mlf_env_new(i64 3)
  %v5907 = getelementptr i8, ptr %v5906, i64 24
  store ptr %v28, ptr %v5907, align 8, !tbaa !3
  %v5908 = getelementptr i8, ptr %v5906, i64 32
  store ptr %v30, ptr %v5908, align 8, !tbaa !3
  %v5909 = getelementptr i8, ptr %v5906, i64 40
  store ptr %arg, ptr %v5909, align 8, !tbaa !3
  %v5910 = call ptr @mlf_closure(ptr @mlf.code.1355, ptr %v5906)
  %v5911 = call ptr @mlf_prim2(i64 1, ptr %v1354, ptr %v5910)
  ret ptr %v5911
}

define private ptr @mlf.code.19(ptr %env, ptr %arg) {
entry:
  %v20 = getelementptr i8, ptr %env, i64 24
  %v21 = load ptr, ptr %v20, align 8, !tbaa !3
  %v25 = call ptr @mlf_thunk(ptr @mlf.code.22, ptr null)
  %v5912 = call ptr @mlf_env_new(i64 2)
  %v5913 = getelementptr i8, ptr %v5912, i64 24
  store ptr %v21, ptr %v5913, align 8, !tbaa !3
  %v5914 = getelementptr i8, ptr %v5912, i64 32
  store ptr %arg, ptr %v5914, align 8, !tbaa !3
  %v5915 = call ptr @mlf_closure(ptr @mlf.code.26, ptr %v5912)
  %v5916 = call ptr @mlf_prim2(i64 1, ptr %v25, ptr %v5915)
  ret ptr %v5916
}

define private ptr @mlf.code.0(ptr %env, ptr %arg) {
entry:
  %v17 = call ptr @mlf_thunk(ptr @mlf.code.1, ptr null)
  %v18 = call ptr @mlf_primitive(i64 4)
  %v5917 = call ptr @mlf_env_new(i64 1)
  %v5918 = getelementptr i8, ptr %v5917, i64 24
  store ptr %v17, ptr %v5918, align 8, !tbaa !3
  %v5919 = call ptr @mlf_closure(ptr @mlf.code.19, ptr %v5917)
  %v5920 = call ptr @mlf_prim2(i64 1, ptr %v18, ptr %v5919)
  ret ptr %v5920
}

declare void @mlf_require_standard_abi()
define ptr @mlf_entry() {
  call void @mlf_require_standard_abi()
  %root = call ptr @mlf.code.0(ptr null, ptr null)
  ret ptr %root
}
define i32 @main(i32 %argc, ptr %argv) {
  call void @mlf_set_args(i32 %argc, ptr %argv)
  %root = call ptr @mlf_entry()
  %status = call i32 @mlf_run(ptr %root, i64 1)
  ret i32 %status
}
