"""Pure fixed sampling ledger and duration contracts. No execution or IO."""
def require(value,message):
    if not value:raise ValueError(message)

def prefix(block,failed_ns,completion_ns,block1_ns=None):
    require(type(block) is int and block in (1,2),'fixed block1/2')
    require(type(failed_ns) is int and failed_ns==596647140326,'real failed semantic duration never reset')
    require(type(completion_ns) is int and 0<=completion_ns<=180*10**9,'actual independently accepted completion duration')
    if block==1:
        require(block1_ns is None,'block1 has no preceding sampling result');exploration=0
    else:
        require(type(block1_ns) is int and 0<=block1_ns<=600*10**9,'actual accepted block1 duration');exploration=block1_ns
    qualification=failed_ns+completion_ns
    require(exploration+600*10**9<=1200*10**9 and qualification+exploration+600*10**9<=1800*10**9,'full next cap must fit both ceilings, otherwise stop')
    return {'failed_semantic_ns':failed_ns,'completion_ns':completion_ns,'qualification_ns':qualification,
            'sampling_prior_ns':exploration,'post_setup_prior_ns':qualification+exploration}

def poststage(prior,elapsed_ns):
    require(type(elapsed_ns) is int and 0<=elapsed_ns<=600*10**9,'complete actual returned-call stage duration')
    require(prior['sampling_prior_ns']+elapsed_ns<=1200*10**9 and prior['post_setup_prior_ns']+elapsed_ns<=1800*10**9,'actual cumulative duration ceilings')
    return {'elapsed_ns':elapsed_ns,'sampling_cumulative_ns':prior['sampling_prior_ns']+elapsed_ns,'post_setup_cumulative_ns':prior['post_setup_prior_ns']+elapsed_ns}

def resolved_rows(ledger,qualified_rows,accepted_semantic,block):
    require(type(block) is int and block in (1,2) and accepted_semantic['combined_qualification_accepted'] is True,'actual semantic independent acceptance required')
    require(len(ledger['rows'])==64 and ledger['measured_legs']==48 and ledger['mandatory_RTS_reports']==48,'fixed64/48 ledger')
    originals={r['ordinal']:r for r in qualified_rows};rows=[]
    for row in ledger['rows']:
        if row['block']!=block:continue
        if row['kind']=='runtime':
            binding=accepted_semantic['worker']['runtime_after'][row['role']]
            value={'kind':'runtime','label':'runtime-'+row['role']+'-'+row['when'],'maximum_seconds':10,
                'argv_template':[binding['loader']['resolved'],'--list',binding['executable']['resolved']],
                'expected_exit':0,'expected_stderr_utf8':''}
        else:
            require(row['kind']=='measured_leg','only fixed measured/support kinds')
            source=originals[row['qualified_command_template_ordinal']]
            require(source['cell']==row['cell'] and source['kind']==('stats_compile' if row['lane']=='M' else 'ghc_typed'),'same qualified endpoint')
            require(type(row['maximum_seconds']) is int and 0<row['maximum_seconds']<=source['maximum_seconds'],'sampling cap only tightens qualified child maximum')
            witness=accepted_semantic['cells'][row['cell']]
            require(source['argv_template']==witness['stats_argv' if row['lane']=='M' else 'ghc_argv'],'unchanged actually qualified target argv')
            value=dict(source);value.update(kind='measured_leg',label='leg-'+row['leg_id'],maximum_seconds=row['maximum_seconds'],
                leg_ordinal=row['leg_ordinal'],leg_id=row['leg_id'],lane=row['lane'],within_cell=row['within_cell'])
        value['ordinal']=len(rows)+1;rows.append(value)
    measured=[r for r in rows if r['kind']=='measured_leg']
    require(len(rows)==32 and len(measured)==24 and [r['leg_ordinal'] for r in measured]==list(range((block-1)*24+1,block*24+1)), 'fixed consecutive block')
    require(all([r['lane'] for r in measured[i:i+4]]==['M','G','G','M'] for i in range(0,24,4)), 'fixed MGGM groups')
    return rows
