/* Shared by the real Windows runtime suite and the portable GMP LLP64 probe.
 * Include after mlf_runtime.c and the test's require/eq helpers. */
static void check_numeric_widths(void) {
    require(eq(show_integer(mlf_add_int(mlf_integer("4294967296"),mlf_integer("4611686018427387903"))),"4611686022722355199"),"Int64 tagged/full-width addition");
    require(eq(show_integer(mlf_sub_int(mlf_integer("-4611686018427387904"),mlf_integer("4294967296"))),"-4611686022722355200"),"Int64 tagged/full-width subtraction");
    require(eq(show_integer(mlf_prim2(MUL_INT,mlf_integer("4294967296"),mlf_integer("4294967296"))),"0"),"Int64 multiplication wraps");
    require(eq(show_integer(mlf_add_int(mlf_integer("9223372036854775807"),mlf_integer("1"))),"-9223372036854775808"),"Int64 addition wraps");
    require(eq(show_integer(mlf_integer("18446744073709551615")),"-1"),"Int64 literal wraps");
    require(mlf_truth(mlf_lt_int(mlf_integer("4294967296"),mlf_integer("9223372036854775807"))),"full-width Int64 comparison");
    require(bounded_integer(mlf_integer("9223372036854775807"),UINT64_MAX,"wide bound")==INT64_MAX,"nonnegative Int64 bound");
    require(eq(show_integer(double_to_bits(mlf_double(-1.0))),"-4616189618054758400"),"signed Int64 double bits");
    require(eq(show_big_integer(big_integer_extended(MUL_INTEGER,big_integer("4294967296"),big_integer("4294967296"))),"18446744073709551616"),"explicit Integer multiplication remains unbounded");
    require(big_integer_compare(big_integer("4294967296"),big_integer("18446744073709551616"))<0,"unbounded Integer comparison");
    require(eq(show_big_integer(int_to_integer(mlf_integer("-9223372036854775808"))),"-9223372036854775808"),"Int64 minimum to Integer");
    require(eq(show_integer(integer_to_int(big_integer("18446744073709551619"))),"3"),"Integer positive low 64 bits");
    require(eq(show_integer(integer_to_int(big_integer("-18446744073709551617"))),"-1"),"Integer negative low 64 bits");
}
