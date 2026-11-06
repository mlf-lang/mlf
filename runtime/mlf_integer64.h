/* GMP's signed/unsigned long interface is 32-bit on Win64 (LLP64).
 * Preserve the runtime's 64-bit tagged integers without changing POSIX code. */
#ifndef MLF_INTEGER64_H
#define MLF_INTEGER64_H
#if LONG_MAX < INT64_MAX
static void mlf_z_set_u64(mpz_ptr z, uint64_t n) { mpz_import(z,1,1,sizeof(n),0,0,&n); }
static void mlf_z_set_i64(mpz_ptr z, int64_t n) {
    mlf_z_set_u64(z,n < 0 ? -(uint64_t)n : (uint64_t)n);
    if (n < 0) mpz_neg(z,z);
}
static uint64_t mlf_z_get_u64(mpz_srcptr z) {
    uint64_t n = 0;
    mpz_t low; mpz_init(low); mpz_tdiv_r_2exp(low,z,64);
    mpz_export(&n,NULL,1,sizeof(n),0,0,low); mpz_clear(low); return n;
}
static int64_t mlf_z_get_i64(mpz_srcptr z) {
    uint64_t n = mlf_z_get_u64(z);
    return (int64_t)(mpz_sgn(z) < 0 ? -n : n);
}
static inline int mlf_z_fits_u64(mpz_srcptr z) { return mpz_sgn(z) >= 0 && mpz_sizeinbase(z,2) <= 64; }
static int mlf_z_fits_i64(mpz_srcptr z) {
    size_t bits = mpz_sizeinbase(z,2);
    return bits < 64 || (bits == 64 && mpz_sgn(z) < 0 && mlf_z_get_u64(z) == (UINT64_C(1)<<63));
}
static void mlf_z_init_i64(mpz_ptr z, int64_t n) { mpz_init(z); mlf_z_set_i64(z,n); }
static void mlf_z_init_u64(mpz_ptr z, uint64_t n) { mpz_init(z); mlf_z_set_u64(z,n); }
static int mlf_z_cmp_i64(mpz_srcptr z, int64_t n) {
    mpz_t v; mlf_z_init_i64(v,n); int result = mpz_cmp(z,v); mpz_clear(v); return result;
}
static void mlf_z_add_u64(mpz_ptr z, mpz_srcptr a, uint64_t n) {
    mpz_t v; mlf_z_init_u64(v,n); mpz_add(z,a,v); mpz_clear(v);
}
static void mlf_z_sub_u64(mpz_ptr z, mpz_srcptr a, uint64_t n) {
    mpz_t v; mlf_z_init_u64(v,n); mpz_sub(z,a,v); mpz_clear(v);
}
static void mlf_z_mul_i64(mpz_ptr z, mpz_srcptr a, int64_t n) {
    mpz_t v; mlf_z_init_i64(v,n); mpz_mul(z,a,v); mpz_clear(v);
}
#undef mpz_get_si
#undef mpz_get_ui
#undef mpz_set_si
#undef mpz_init_set_si
#undef mpz_init_set_ui
#undef mpz_cmp_si
#undef mpz_add_ui
#undef mpz_sub_ui
#undef mpz_mul_si
#undef mpz_fits_slong_p
#undef mpz_fits_ulong_p
#define mpz_get_si mlf_z_get_i64
#define mpz_get_ui mlf_z_get_u64
#define mpz_set_si mlf_z_set_i64
#define mpz_init_set_si mlf_z_init_i64
#define mpz_init_set_ui mlf_z_init_u64
#define mpz_cmp_si mlf_z_cmp_i64
#define mpz_add_ui mlf_z_add_u64
#define mpz_sub_ui mlf_z_sub_u64
#define mpz_mul_si mlf_z_mul_i64
#define mpz_fits_slong_p mlf_z_fits_i64
#define mpz_fits_ulong_p mlf_z_fits_u64
#endif
#endif
