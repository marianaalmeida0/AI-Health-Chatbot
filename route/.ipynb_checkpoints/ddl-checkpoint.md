-- Tabela: con_marcacoes 
-- Contém consultas futuras (ou presentes). A data está no formato DATE.
-- Usa-se diretamente nas comparações (ex: c.dta_consulta > CURRENT_DATE).
-- Para exibição formatada, usa TO_CHAR(c.dta_consulta, 'DD/MM/YYYY').
-- cod_med_esp liga a médico ou especialidade, dependendo de tip_agenda.

CREATE TABLE con_marcacoes (
    num_sequencial SERIAL , --numero identificador do paciente
    cod_med_esp INTEGER NOT NULL, -- relacao medico ou especialidade - tip_agenda = M (vai ao medico) / E - sysespecialidade)  (
    tip_consulta VARCHAR(10), -- P - primeira consulta ; S - Ou consulta Subsequente
    dta_consulta date, --data para a qual a consulta está agendada
    hora_consulta INTEGER NOT NULL, -- hora agendada para a consulta em segundos
    cod_sala VARCHAR(10), --sala onde está agendada realizado
    cod_especialidade INTEGER, --especialidade liga com a sys_especialidades
    tip_agenda CHAR(1), -- M - Médico, E - Especialidade
    PRIMARY KEY (num_sequencial, dta_consulta, hora_consulta)
);

-- Tabela: con_med_esp
-- Relação entre médicos e especialidades. Utilizada em marcações.
-- cod_medico refere-se a sys_medicos; cod_especialidade a sys_especialidades.

CREATE TABLE con_med_esp (
    cod_med_esp INTEGER PRIMARY KEY, -- cod_med_esp da tabela con_marcacoes
    cod_especialidade INTEGER NOT NULL, -- cod_especialidade da sys_especialidades
    cod_medico INTEGER NOT NULL -- num_ord_medico da sys_medicos
);

-- Tabela: sys_medicos
-- Lista dos médicos disponíveis, identificados pelo número de ordem (num_ord_medico).
CREATE TABLE sys_medicos (
    num_ord_medico INTEGER PRIMARY KEY, --numero da ordem do médico
    nome TEXT -- nome
);


-- Tabela: sys_especialidades
-- Lista de especialidades clínicas. cod_especialidade é usado em marcações e exames.

create table sys_especialidades (
    cod_especialidade integer primary key, --codigo
    des_especialidade varchar(400) --descricao
);

-- Tabela: con_registadas ( consultas já realizadas)
-- Contém consultas já realizadas (passadas). A data está em formato DATE.
-- Usa-se diretamente em comparações ou formatação com TO_CHAR.
-- cod_med_esp funciona como em con_marcacoes, com base em tip_agenda.

CREATE TABLE con_registadas (
    episodio INTEGER PRIMARY KEY, --numero indetificador da visita do paciente (unico)
    num_sequencial INTEGER, -- numero identificador do paciente
    cod_med_esp INTEGER NOT NULL, -- relacao medico ou especialidade - tip_agenda = M (agenda medico) / E - sysespecialidade)
    tip_consulta VARCHAR(10), -- P - primeira consulta ; S - Ou consulta Susequente
    dta_realizacao DATE, -- data da consulta
    hora_realizacao INTERGER, -- hora da consulta já realizada em segundos
    cod_sala VARCHAR(10),  --sala onde é realizado
    cod_especialidade INTEGER, --especialidade liga com a sys_especialidades
    tip_agenda CHAR(1) -- M - Médico, E - Especialidade
);

-- Tabela: dpedidos
-- Pedidos de exames efetuados durante episódios clínicos. Liga-se a pacientes e ao episódio da consulta.
-- Contém informação sobre serviço, modalidade, data do pedido, e estado de agendamento/realização.

CREATE TABLE dpedidos (
    numpedido INTEGER PRIMARY KEY, -- numero identificador do pedido
    episodio INTEGER, --numero indetificador da visita do paciente
    modulo VARCHAR(50), -- 'CON'; 'INT', 'URG', 'BLO', 'HDI'
    designamodulo VARCHAR(100), --designacao do modulo: 'Consulta', 'Internamento', 'Urgência', 'Bloco', 'Hospital de Dia'
    idser VARCHAR(20), -- serviço executante ('CARD','PNEUMO','GASTRO')
    servico VARCHAR(100), -- designação do serviço: 'Cardiologia, Pneumologia, Gastro')
    datapedido DATE, -- data de realização do pedido
    posto VARCHAR(20), -- posto para o qual vai ser agendado
    num_sequencial INTEGER,  --numero indetificador da visita do paciente
    datanascimento DATE, -- data de nascimento
    sexo CHAR(1), -- sexo ( 1- Masculino ; 2- Feminino)
    modalidade VARCHAR(50), -- modalidade de execução do exame: 'PNEUMO','CH' - Holter, 'ECG','CM' - MAPA,'GASTRO' (é um agrupador de atos e corresponde à modalidade da tabela tabigif)
    numexame INTEGER, -- preenchido quando há um exame realizado para este pedido
    marcado VARCHAR(1), -- Estado do pedido 0 - pedido, 1 - agendado, 2- rececionado, 3- em execução, 4 - realizado
    fechado VARCHAR(1), -- 0 não terminado, 1 fechado
    segura VARCHAR(1), -- nulo: exame no estado correto; > 8 - anulado ou cancelado
    utiliza VARCHAR(50), -- num mecanografico do utilziador que agendou o exame
    dataexame DATE -- data de realização do exame(quando realizado)
);

-- Tabela: pedidos
-- Atos médicos associados a um pedido (dpedidos). Cada pedido pode conter vários atos (exames).
-- Usa cod_pedido (ligado a tabigif) e tem ordem para identificar sequência dos atos.

CREATE TABLE pedidos (
    numpedido VARCHAR, --identificador do pedido que corresponde ao numpedido da tabela dpedidos
    ordem INTEGER, -- se tiver mais do que um ato medico a realizar são ordenados por aqui
    idser VARCHAR(20), -- serviço executante ('CARD','PNEUMO','GASTRO')
    modalidade VARCHAR(50), -- modalidade de execução do exame: 'PNEUMO','CH' - Holter, 'ECG','CM' - MAPA,'GASTRO' (é um agrupador de atos e corresponde à modalidade da tabela tabigif)
    cod_pedido VARCHAR(50), -- cigif da tabela tabigif e é o codigo identificado do ato medico a realizar
    des_pedido TEXT, -- digif da tabela tabigif e é a descrição do ato medico a realizar
    PRIMARY KEY (numpedido, ordem)
);

-- Tabela: dexames
-- Instâncias de exames realizados ou agendados. Relaciona-se com pacientes e pedidos.
-- Contém dados como data do exame (DATE), serviço, relatório e path para PDF.

CREATE TABLE dexames (
    numexame VARCHAR PRIMARY KEY, -- número identificador do exame
    episodio INTEGER, --numero indetificador da visita do paciente
    modulo VARCHAR(50), -- tipo de contexto clínico em que o exame foi realizado : 'CON'; 'INT', 'URG', 'BLO', 'HDI'
    designamodulo VARCHAR(100), --designacao do modulo: 'Consulta', 'Internamento', 'Urgência', 'Bloco', 'Hospital de Dia'
    idser VARCHAR(20), -- serviço executante ('CARD','PNEUMO','GASTRO')
    servico VARCHAR(100), -- designação do serviço: 'Cardiologia, Pneumologia, Gastro')
    datapedido DATE, -- data de realização do pedido
    posto VARCHAR(20), -- posto para o qual vai ser agendado
    num_sequencial INTEGER,  --numero indetificador do paciente
    datanascimento DATE,  -- data de nascimento
    sexo CHAR(1), -- sexo ( 1- Masculino ; 2- Feminino)
    modalidade VARCHAR(50), -- modalidade de execução do exame: 'PNEUMO','CH' - Holter, 'ECG','CM' - MAPA,'GASTRO' (é um agrupador de atos e corresponde à modalidade da tabela tabigif)
    relatorio TEXT, --texto final do relatorio (normalmente encriptado)
    pathrelatorio TEXT, --link para o pdf do relatorio
    fechado VARCHAR(1), -- 0 não terminado, 1 fechado
    segura VARCHAR(1), -- nulo: exame no estado correto; > 8 - anulado ou cancelado
    utiliza VARCHAR(50), -- num mecanografico do utilziador que realizou o exame
    dataexame DATE -- data de realização do exame(quando realizado)
);

-- Tabela: exames
-- Detalhes técnicos dos exames realizados, com código, designação, verificação e faturação.
-- Liga-se a dexames por numexame e à tabela de atos (tabigif) por codigif.

CREATE TABLE exames (
    numexame VARCHAR, --identificador do exame que corresponde ao numexame da tabela dexames
    versao INTEGER, --se tiver mais do que uma versão começa no valor 1
    ordem INTEGER, --se tiver mais do que um ato medico a realizar são ordenados por aqui
    idser VARCHAR(20), -- serviço executante ('CARD','PNEUMO','GASTRO')
    codigif VARCHAR(20), -- cigif da tabela tabigif e é o codigo identificador do ato medico realizado
    designacaoigif VARCHAR(100), -- digif da tabela tabigif e é a descrição do ato medico realizado
    verificado VARCHAR(1), -- 0 não verificado, 1 verificado, 2- com erro
    facturado VARCHAR(1),--  0 não faturado, 1 faturado, 2- com erro
    PRIMARY KEY (numexame, versao, ordem)
);

-- Tabela: pacientes
CREATE TABLE pacientes (
    num_sequencial INTEGER PRIMARY KEY, --numero indetificador da visita do paciente
    nome VARCHAR(20), --nome do doente
    data_nascimento date, -- data de nascimento
    sexo VARCHAR(1), -- sexo ( 1- Masculino ; 2- Feminino)
    num_processo    integer -- numero do processo do paciente
    
    
);
-- Tabela: con_diarios
-- Registos de texto clínico (diários) criados pelo médico durante o episódio da consulta.

CREATE TABLE con_diarios (
    id_diario INTEGER PRIMARY KEY, --numero indetificador do diario
    episodio INTEGER, --numero indetificador da visita do paciente
    diario VARCHAR(4000), -- texto do diário
    cod_medico integer, --num_ordem_medico
    data_diario date -- data de execução do diário
);

-- Tabela: tabigif
-- Catálogo de atos médicos possíveis. Define códigos e designações (cigif e digif).
-- Também identifica o serviço e modalidade a que pertencem os atos.

create table tabigif (
    cigif varchar(6) primary key, -- codigo identificador do ato medico
    idser varchar(6), -- código do serviço executante ('CARD','PNEUMO','GASTRO')
    servico varchar(20), -- descrição do serviço executante ('Cardiologia, Pneumologia, Gastro')
    modalidade varchar(6), -- modalidade agrupadora de atos ('PNEUMO','CH' - Holter, 'ECG','CM' - MAPA,'GASTRO')
    digif varchar(400), -- descrição do ato medico
    tipo_am varchar(1), -- tipo do exame M-MCDTs, A-Análise
    ativo varchar(1) -- Se esta ativo ou não 0-não;1-sim
);

-- con_med_esp -> sys_medicos
ALTER TABLE con_med_esp ADD CONSTRAINT fk_medesp_medico FOREIGN KEY (cod_medico) REFERENCES sys_medicos(num_ord_medico);

-- dpedidos -> pacientes
ALTER TABLE dpedidos ADD CONSTRAINT fk_dpedidos_paciente FOREIGN KEY (num_sequencial) REFERENCES pacientes(num_sequencial);

-- dpedidos -> con_registadas
ALTER TABLE dpedidos ADD CONSTRAINT fk_dpedidos_episodio FOREIGN KEY (episodio) REFERENCES con_registadas(episodio);

-- pedidos -> dpedidos
ALTER TABLE pedidos ADD CONSTRAINT fk_pedidos_dpedidos FOREIGN KEY (numpedido) REFERENCES dpedidos(numpedido);

-- pedidos -> atos
ALTER TABLE pedidos ADD CONSTRAINT fk_pedidos_atos FOREIGN KEY (cod_pedido) REFERENCES tabigif(cigif);

-- dexames -> con_registadas
ALTER TABLE dexames ADD CONSTRAINT fk_dexames_episodio FOREIGN KEY (episodio) REFERENCES con_registadas(episodio);

-- dexanes -> paciente
ALTER TABLE dexames ADD CONSTRAINT fk_dexanes_paciente FOREIGN KEY (num_sequencial) REFERENCES pacientes(num_sequencial);

-- dexames -> exames
ALTER TABLE exames ADD CONSTRAINT fk_exames_dexames FOREIGN KEY (numexame) REFERENCES dexames(numexame);

-- exames -> atos
ALTER TABLE exames ADD CONSTRAINT fk_exames_atos FOREIGN KEY (coDIGIF) REFERENCES tabigif(cigif);

-- diarios -> exames
ALTER TABLE con_diarios ADD CONSTRAINT fk_diario_consulta FOREIGN KEY (episodio) REFERENCES con_registadas(episodio);

-- con_med_esp -> sys_medicos
ALTER TABLE con_diarios ADD CONSTRAINT fk_cod_medico FOREIGN KEY (cod_medico) REFERENCES sys_medicos(num_ord_medico);

-- con_med_esp -> sys_especialidades
ALTER TABLE con_med_esp ADD CONSTRAINT fk_cod_med_especialidade FOREIGN KEY (cod_especialidade) REFERENCES sys_especialidades(cod_especialidade);
